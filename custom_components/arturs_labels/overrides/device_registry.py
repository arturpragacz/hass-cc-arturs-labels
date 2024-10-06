"""Provide a registry for devices."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import logging
from typing import Any, TypedDict, cast

import attr

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as old_dr  # noqa: ICN001
from homeassistant.helpers.json import json_fragment
from homeassistant.helpers.registry import RegistryIndexType
from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.util.event_type import EventType
from homeassistant.util.hass_dict import HassKey

from . import label_registry as lr
from .registry import (
    RegistryEntryBase,
    async_get_effective_labels,
    under_cached_property,
)

_LOGGER = logging.getLogger(__name__)

DATA_REGISTRY: HassKey[DeviceRegistry] = HassKey("arturs_device_registry")

EVENT_DEVICE_REGISTRY_LABELS_UPDATE: EventType[EventDeviceRegistryLabelsUpdateData] = (
    EventType("arturs_device_registry_labels_update")
)


class EventDeviceRegistryLabelsUpdateData(TypedDict):
    """Event data for when the device labels are updated."""

    device_id: str


type EventDeviceRegistryLabelsUpdate = Event[EventDeviceRegistryLabelsUpdateData]


@attr.s(slots=True, frozen=True, kw_only=True)
class DeviceEntry(RegistryEntryBase, old_dr.DeviceEntry):
    """Device Registry Entry."""

    @property
    def dict_repr(self) -> dict[str, Any]:
        """Return a dict representation of the entry."""
        result = super().dict_repr
        result["labels"] = self._frontend_labels
        result["area_id"] = self.shadow_area_id
        return result

    @under_cached_property
    def as_storage_fragment(self) -> json_fragment:
        """Return a json fragment for storage."""
        self.set_area_id_shadow(False)
        result = super().as_storage_fragment
        self.set_area_id_shadow(True)
        return result


class ActiveDeviceRegistryItems(old_dr.ActiveDeviceRegistryItems):
    """Container for active device registry items, maps device id -> entry.

    Maintains one additional index over base class:
    - effective_label -> dict[key, True]
    """

    view: Mapping[str, DeviceEntry]
    hass: HomeAssistant
    no_devices_for_label: bool = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the container."""
        super().__init__()
        self.view = self.data  # type: ignore [assignment]
        self.hass = hass
        self._effective_labels_index: RegistryIndexType = defaultdict(dict)

    def _index_entry(self, key: str, entry: old_dr.DeviceEntry) -> None:
        """Index an entry."""
        wrong_type = type(entry) is not DeviceEntry
        if wrong_type or cast(DeviceEntry, entry).extra_labels_init:
            lab_reg = lr.async_get(self.hass)

            effective_labels = async_get_effective_labels(lab_reg, entry.labels)

            if wrong_type:
                entry_dict = attr.asdict(
                    entry, filter=lambda a, _v: a.init, retain_collection_types=True
                )
                entry = DeviceEntry(
                    **entry_dict,
                    effective_labels=effective_labels,
                )
            else:
                entry = cast(DeviceEntry, entry)
                entry = attr.evolve(
                    entry,
                    effective_labels=effective_labels,
                )

            self.data[key] = entry
        else:
            entry = cast(DeviceEntry, entry)
            entry.set_extra_labels_init()

        super()._index_entry(key, entry)

        # if (area_id := entry.shadow_area_id) is not None:
        #     self._area_id_index[area_id][key] = True
        for label in entry.effective_labels:
            self._effective_labels_index[label][key] = True

    def _unindex_entry(
        self,
        key: str,
        replacement_entry: old_dr.DeviceEntry | None = None,
    ) -> None:
        """Unindex an entry."""
        entry = self.view[key]

        entry.set_area_id_shadow(True)

        super()._unindex_entry(key, replacement_entry)

        # if area_id := entry.shadow_area_id:
        #     self._unindex_entry_value(key, area_id, self._area_id_index)
        if effective_labels := entry.effective_labels:
            for label in effective_labels:
                self._unindex_entry_value(key, label, self._effective_labels_index)

    def get_devices_for_label(
        self, label: str, effective: bool = True
    ) -> list[old_dr.DeviceEntry]:
        """Get devices for label."""
        if self.no_devices_for_label:
            return []
        if effective:
            index = self._effective_labels_index
        else:
            index = self._labels_index
        view = self.view
        return [view[key] for key in index.get(label, ())]


class DeviceRegistry(old_dr.DeviceRegistry):
    """Class to hold a registry of devices."""

    devices: ActiveDeviceRegistryItems

    _old_registry: old_dr.DeviceRegistry

    def __init__(
        self, hass: HomeAssistant, old_registry: old_dr.DeviceRegistry
    ) -> None:
        """Initialize the device registry."""
        # pylint: disable=super-init-not-called
        self.hass = hass
        self._old_registry = old_registry
        self._store = old_registry._store  # noqa: SLF001

    @callback
    def async_update_device(self, device_id: str, **kwargs) -> DeviceEntry | None:
        """Update properties of a device."""
        old_entry = self.devices.view[device_id]

        fire = False

        labels = kwargs.get("labels", UNDEFINED)
        if labels is None or labels == old_entry.labels:
            old_entry.set_extra_labels_init(False)
        else:
            fire = True

        old_entry.set_area_id_shadow(False)

        try:
            new_entry = super().async_update_device(device_id, **kwargs)
        finally:
            # in case the entry didn't change
            old_entry.set_extra_labels_init()
            old_entry.set_area_id_shadow(True)

        if new_entry is None:
            return None

        if fire:
            self.hass.bus.async_fire(
                EVENT_DEVICE_REGISTRY_LABELS_UPDATE,
                EventDeviceRegistryLabelsUpdateData(
                    device_id=device_id,
                ),
            )

        # can change during indexing, so always get the fresh one
        return self.devices.view[device_id]

    async def async_load(self) -> None:
        """Erase method."""
        raise NotImplementedError

    @callback
    def async_load_cb(self) -> None:
        """Load the device registry."""
        _async_setup_labels(self.hass, self)

        devices = ActiveDeviceRegistryItems(self.hass)
        devices.update(self._old_registry.devices)

        self.devices = devices
        self._device_data = devices.data
        self.deleted_devices = self._old_registry.deleted_devices

        self._old_registry.devices = self.devices
        self._old_registry._device_data = self._device_data  # noqa: SLF001
        self._old_registry.__class__ = self.__class__

    @callback
    def async_clear_label_id(self, label_id: str) -> None:
        """Clear label from registry entries."""
        for device in self.devices.get_devices_for_label(label_id, effective=False):
            self.async_update_device(device.id, labels=device.labels - {label_id})

    @callback
    def async_update_extra_labels(self) -> None:
        """Update extra labels in registry entries."""
        lab_reg = lr.async_get(self.hass)

        for device_id, entry in self.devices.view.items():
            effective_labels = async_get_effective_labels(lab_reg, entry.labels)
            if effective_labels == entry.effective_labels:
                continue

            self.devices[device_id] = attr.evolve(
                entry, effective_labels=effective_labels, extra_labels_init=False
            )

            data: old_dr._EventDeviceRegistryUpdatedData_Update = {
                "action": "update",
                "device_id": device_id,
                "changes": {},
            }

            self.hass.bus.async_fire(old_dr.EVENT_DEVICE_REGISTRY_UPDATED, data)


@callback
@singleton(DATA_REGISTRY)
def async_get(hass: HomeAssistant) -> DeviceRegistry:
    """Get device registry."""
    old_registry = old_dr.async_get(hass)
    return DeviceRegistry(hass, old_registry)


@callback
def async_load(hass: HomeAssistant) -> None:
    """Load device registry."""
    assert DATA_REGISTRY not in hass.data
    async_get(hass).async_load_cb()
    old_dr.async_get = async_get


@callback
def _async_setup_labels(hass: HomeAssistant, registry: DeviceRegistry) -> None:
    """Respond to labels extra updated."""

    @callback
    def _handle_label_registry_extra_update(
        event: lr.EventLabelRegistryExtraUpdated,
    ) -> None:
        registry.async_update_extra_labels()

    hass.bus.async_listen(
        event_type=lr.EVENT_LABEL_REGISTRY_EXTRA_UPDATED,
        listener=_handle_label_registry_extra_update,
    )
