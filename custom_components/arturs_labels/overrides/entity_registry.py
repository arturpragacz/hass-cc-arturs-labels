"""Provide a registry for entities."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from functools import cached_property
import logging
from typing import Any, cast

import attr

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    device_registry as old_dr,  # noqa: ICN001
    entity_registry as old_er,  # noqa: ICN001
)
from homeassistant.helpers.json import json_fragment
from homeassistant.helpers.registry import RegistryIndexType
from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.util.hass_dict import HassKey

from . import device_registry as dr, label_registry as lr
from .registry import RegistryEntryBase, async_get_effective_labels

_LOGGER = logging.getLogger(__name__)

DATA_REGISTRY: HassKey[EntityRegistry] = HassKey("arturs_entity_registry")


@attr.s(frozen=True)
class RegistryEntry(RegistryEntryBase, old_er.RegistryEntry):
    """Entity Registry Entry."""

    assigned_labels: set[str] = attr.ib(factory=set)

    @property
    def _as_display_dict(self) -> dict[str, Any] | None:
        """Return a partial dict representation of the entry.

        This version only includes what's needed for display.
        Returns None if there's no data needed for display.
        """
        display_dict = cast(dict[str, Any], super()._as_display_dict)
        display_dict["lb"] = self._frontend_labels
        display_dict["ai"] = self.shadow_area_id
        return display_dict

    @cached_property
    def as_partial_dict(self) -> dict[str, Any]:
        """Return a partial dict representation of the entry."""
        partial_dict = super().as_partial_dict
        partial_dict["labels"] = self._frontend_labels
        partial_dict["area_id"] = self.shadow_area_id
        return partial_dict

    @cached_property
    def as_storage_fragment(self) -> json_fragment:
        """Return a json fragment for storage."""
        self.set_area_id_shadow(False)
        result = super().as_storage_fragment
        self.set_area_id_shadow(True)
        return result


class EntityRegistryItems(old_er.EntityRegistryItems):
    """Container for entity registry items, maps entity_id -> entry.

    Maintains one additional index over base class:
    - effective_label -> dict[key, True]
    """

    view: Mapping[str, RegistryEntry]
    hass: HomeAssistant

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the containold_er."""
        super().__init__()
        self.view = self.data  # type: ignore [assignment]
        self.hass = hass
        self._effective_labels_index: RegistryIndexType = defaultdict(dict)

    def _index_entry(self, key: str, entry: old_er.RegistryEntry) -> None:
        """Index an entry."""
        wrong_type = type(entry) is not RegistryEntry
        if wrong_type or cast(RegistryEntry, entry).extra_labels_init:
            lab_reg = lr.async_get(self.hass)
            dev_reg = old_dr.async_get(self.hass)

            assigned_labels = _async_get_assigned_labels(dev_reg, entry)
            effective_labels = async_get_effective_labels(lab_reg, assigned_labels)

            if wrong_type:
                entry_dict = attr.asdict(
                    entry, filter=lambda a, _v: a.init, retain_collection_types=True
                )
                entry = RegistryEntry(
                    **entry_dict,
                    assigned_labels=assigned_labels,
                    effective_labels=effective_labels,
                )
            else:
                entry = cast(RegistryEntry, entry)
                entry = attr.evolve(
                    entry,
                    assigned_labels=assigned_labels,
                    effective_labels=effective_labels,
                )

            self.data[key] = entry
        else:
            entry = cast(RegistryEntry, entry)
            entry.set_extra_labels_init()

        super()._index_entry(key, entry)

        # if (area_id := entry.shadow_area_id) is not None:
        #     self._area_id_index[area_id][key] = True
        for label in entry.effective_labels:
            self._effective_labels_index[label][key] = True

    def _unindex_entry(
        self,
        key: str,
        replacement_entry: old_er.RegistryEntry | None = None,
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

    def get_entries_for_label(
        self, label: str, effective: bool = True
    ) -> list[old_er.RegistryEntry]:
        """Get entries for label."""
        if effective:
            index = self._effective_labels_index
        else:
            index = self._labels_index
        view = self.view
        return [view[key] for key in index.get(label, ())]


class EntityRegistry(old_er.EntityRegistry):
    """Class to hold a registry of entities."""

    entities: EntityRegistryItems

    _old_registry: old_er.EntityRegistry

    def __init__(
        self, hass: HomeAssistant, old_registry: old_er.EntityRegistry
    ) -> None:
        """Initialize the entity registry."""
        # pylint: disable=super-init-not-called
        self.hass = hass
        self._old_registry = old_registry
        self._store = old_registry._store  # noqa: SLF001

    @callback
    def async_update_entity(self, entity_id: str, **kwargs) -> RegistryEntry:
        """Update properties of an entity."""
        old_entry = self.entities.view[entity_id]

        labels = kwargs.get("labels", UNDEFINED)
        device_id = kwargs.get("device_id", UNDEFINED)
        if (labels is UNDEFINED or labels == old_entry.labels) and (
            device_id is UNDEFINED or device_id == old_entry.device_id
        ):
            old_entry.set_extra_labels_init(False)

        old_entry.set_area_id_shadow(False)

        try:
            new_entry = super().async_update_entity(entity_id, **kwargs)
            entity_id = new_entry.entity_id  # could change during update
        finally:
            # in case the entry didn't change
            old_entry.set_extra_labels_init()
            old_entry.set_area_id_shadow(True)

        # can change during indexing, so always get the fresh one
        # although we don't care in async_get_or_create, so maybe here we don't have to also
        return self.entities.view[entity_id]

    async def async_load(self) -> None:
        """Erase method."""
        raise NotImplementedError

    @callback
    def async_load_cb(self) -> None:
        """Load the entity registry."""
        _async_setup_labels(self.hass, self)

        entities = EntityRegistryItems(self.hass)
        entities.update(self._old_registry.entities)

        self.entities = entities
        self._entities_data = entities.data
        self.deleted_entities = self._old_registry.deleted_entities

        self._old_registry.entities = self.entities
        self._old_registry._entities_data = self._entities_data  # noqa: SLF001
        self._old_registry.__class__ = self.__class__

    @callback
    def async_clear_label_id(self, label_id: str) -> None:
        """Clear label from registry entries."""
        for entry in self.entities.get_entries_for_label(label_id, effective=False):
            self.async_update_entity(entry.entity_id, labels=entry.labels - {label_id})

    def _async_update_extra_labels(self, filter: Callable[[str], bool]) -> None:
        """Update extra labels in registry entries."""
        lab_reg = lr.async_get(self.hass)
        dev_reg = old_dr.async_get(self.hass)

        for entity_id, entry in self.entities.view.items():
            if not filter(entity_id):
                continue

            assigned_labels = _async_get_assigned_labels(dev_reg, entry)
            effective_labels = async_get_effective_labels(lab_reg, assigned_labels)
            if (
                assigned_labels == entry.assigned_labels
                and effective_labels == entry.effective_labels
            ):
                continue

            self.entities[entity_id] = attr.evolve(
                entry,
                assigned_labels=assigned_labels,
                effective_labels=effective_labels,
                extra_labels_init=False,
            )

            data: old_er._EventEntityRegistryUpdatedData_Update = {
                "action": "update",
                "entity_id": entity_id,
                "changes": {},
            }

            self.hass.bus.async_fire(old_er.EVENT_ENTITY_REGISTRY_UPDATED, data)

    @callback
    def async_update_from_device_extra_labels(self, device_id: str) -> None:
        """Update from device extra labels in registry entries."""
        self._async_update_extra_labels(
            lambda entity_id: self.entities[entity_id].device_id == device_id
        )

    @callback
    def async_update_all_extra_labels(self) -> None:
        """Update all extra labels in registry entries."""
        self._async_update_extra_labels(lambda entity: True)


@callback
@singleton(DATA_REGISTRY)
def async_get(hass: HomeAssistant) -> EntityRegistry:
    """Get entity registry."""
    old_registry = old_er.async_get(hass)
    return EntityRegistry(hass, old_registry)


@callback
def async_load(hass: HomeAssistant) -> None:
    """Load entity registry."""
    assert DATA_REGISTRY not in hass.data
    async_get(hass).async_load_cb()
    old_er.async_get = async_get


@callback
def _async_get_assigned_labels(
    dev_reg: old_dr.DeviceRegistry, entry: old_er.RegistryEntry
) -> set[str]:
    """Get assigned labels for entity."""
    labels = entry.labels

    device_id = entry.device_id
    if device_id is None:
        return labels

    device = dev_reg.async_get(device_id)
    if device is None:
        return labels

    return labels | device.labels


@callback
def _async_setup_labels(hass: HomeAssistant, registry: EntityRegistry) -> None:
    """Clean up entities caches when labels ancestry updated."""

    @callback
    def _handle_label_registry_ancestry_update(
        event: lr.EventLabelRegistryAncestryUpdated,
    ) -> None:
        registry.async_update_all_extra_labels()

    hass.bus.async_listen(
        event_type=lr.EVENT_LABEL_REGISTRY_ANCESTRY_UPDATED,
        listener=_handle_label_registry_ancestry_update,
    )

    @callback
    def _handle_device_registry_labels_update(
        event: dr.EventDeviceRegistryLabelsUpdate,
    ) -> None:
        registry.async_update_from_device_extra_labels(event.data["device_id"])

    hass.bus.async_listen(
        event_type=dr.EVENT_DEVICE_REGISTRY_LABELS_UPDATE,
        listener=_handle_device_registry_labels_update,
    )
