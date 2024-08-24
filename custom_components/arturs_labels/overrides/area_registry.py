"""Provide a registry for areas."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import dataclasses
from dataclasses import dataclass
import logging
from typing import TypedDict

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as old_ar  # noqa: ICN001
from homeassistant.helpers.normalized_name_base_registry import (
    NormalizedNameBaseRegistryItems,
    normalize_name,
)
from homeassistant.helpers.singleton import singleton
from homeassistant.util.event_type import EventType
from homeassistant.util.hass_dict import HassKey

from . import label_registry as lr

_LOGGER = logging.getLogger(__name__)

DATA_REGISTRY: HassKey[AreaRegistry] = HassKey("arturs_area_registry")

NULL_FLOOR_ID: None = None
NULL_LABELS: set[str] = set()

EVENT_AREA_REGISTRY_LABEL_UPDATED: EventType[EventAreaRegistryLabelUpdatedData] = (
    EventType("arturs_area_registry_label_updated")
)


class EventAreaRegistryLabelUpdatedData(TypedDict):
    """Event data for when the label ancestry is updated."""


type EventAreaRegistryLabelUpdated = Event[EventAreaRegistryLabelUpdatedData]

OldAreaEntry = old_ar.AreaEntry


@dataclass(frozen=True, kw_only=True)
class AreaEntry(OldAreaEntry):
    """Area Registry Entry."""

    shadow_floor_id: str | None
    shadow_labels: set[str]


class AreaRegistryItems(old_ar.AreaRegistryItems):
    """Container for area registry items, maps area id -> entry."""

    view: Mapping[str, AreaEntry]

    def __init__(self) -> None:
        """Initialize the container."""
        super().__init__()
        self.view = self.data  # type: ignore [assignment]

    def _index_entry(self, key: str, entry: OldAreaEntry) -> None:
        """Index an entry."""
        if type(entry) is not AreaEntry:
            entry_dict = dataclasses.asdict(entry)
            entry_dict["floor_id"] = NULL_FLOOR_ID
            entry_dict["labels"] = NULL_LABELS

            entry = AreaEntry(
                **entry_dict, shadow_floor_id=entry.floor_id, shadow_labels=entry.labels
            )
            self.data[key] = entry

        super()._index_entry(key, entry)


class LabelRegistryItems(NormalizedNameBaseRegistryItems[OldAreaEntry]):
    """Container for label area registry items, maps area id -> entry."""


class AreaRegistry(old_ar.AreaRegistry):
    """Class to hold a registry of devices."""

    areas: AreaRegistryItems

    _old_registry: old_ar.AreaRegistry
    _label_areas: LabelRegistryItems

    def __init__(self, hass: HomeAssistant, old_registry: old_ar.AreaRegistry) -> None:
        """Initialize the device registry."""
        # pylint: disable=super-init-not-called
        self.hass = hass
        self._old_registry = old_registry
        self._store = old_registry._store  # noqa: SLF001

    @callback
    def async_list_areas(self, active: bool = False) -> Iterable[OldAreaEntry]:
        """Get all label areas."""
        items = self._label_areas if active else self.areas.view
        return items.values()

    @callback
    def _async_create_id(self, id: str, *, name: str) -> OldAreaEntry:
        """Create a new area. Don't fire events."""
        self.hass.verify_event_loop_thread("area_registry.async_create")

        normalized_name = normalize_name(name)

        area = OldAreaEntry(
            aliases=set(),
            floor_id=None,
            icon=None,
            id=id,
            labels=set(),
            name=name,
            normalized_name=normalized_name,
            picture=None,
        )

        self.areas[area.id] = area
        self.async_schedule_save()

        return area

    @callback
    def async_create(self, *args, floor_id=None, labels=None, **kwargs) -> OldAreaEntry:
        """Create a new area."""
        return super().async_create(*args, **kwargs)

    @callback
    def async_delete(self, area_id: str, *args, **kwargs) -> None:
        """Delete area."""
        if area_id in self._label_areas:
            return
        super().async_delete(area_id, *args, **kwargs)

    @callback
    def _async_update_id(self, area_id: str, *, new_area_id: str) -> OldAreaEntry:
        """Delete area. Don't fire events."""
        self.hass.verify_event_loop_thread("area_registry.async_delete")

        old = self.areas[area_id]
        del self.areas[area_id]
        # we don't clear it from entities and devices on purpose

        new = self.areas[new_area_id] = dataclasses.replace(old, id=new_area_id)
        self.async_schedule_save()

        return new

    @callback
    def _async_update(
        self, *args, floor_id=None, labels=None, **kwargs
    ) -> OldAreaEntry:
        """Update properties of an area."""
        area = super()._async_update(*args, **kwargs)

        if area.id in self._label_areas:
            self._label_areas[area.id] = area

        return area

    async def async_load(self) -> None:
        """Erase method."""
        raise NotImplementedError

    @callback
    def async_load_cb(self) -> None:
        """Load the area registry."""
        _async_setup_labels(self.hass, self)

        areas = AreaRegistryItems()
        areas.update(self._old_registry.areas)

        self.areas = areas
        self._area_data = areas.data

        self.async_update_label_areas()

        self._old_registry.areas = self.areas
        self._old_registry._area_data = self._area_data  # noqa: SLF001
        self._old_registry.__class__ = self.__class__

    @callback
    def async_update_label_areas(self) -> None:
        """Update label areas in registry."""
        lab_reg = lr.async_get(self.hass)

        label_areas = LabelRegistryItems()
        areas_created: list[str] = []
        for label_id in lab_reg.areas:
            area = self.async_get_area(label_id)

            if area is None:
                label = lab_reg.async_get_label(label_id)
                assert label is not None
                label_name = label.name
                area = self.async_get_area_by_name(label_name)

                if area is not None:
                    _LOGGER.warning(
                        "Area id %s does not match area label id %s", area.id, label_id
                    )
                    area = self._async_update_id(area.id, new_area_id=label_id)
                else:
                    area = self._async_create_id(label_id, name=label_name)

                areas_created.append(area.id)

            label_areas[area.id] = area

        self._label_areas = label_areas

        for area_id in areas_created:
            self.hass.bus.async_fire(
                old_ar.EVENT_AREA_REGISTRY_UPDATED,
                old_ar.EventAreaRegistryUpdatedData(action="create", area_id=area_id),
            )

        self.hass.bus.async_fire(
            EVENT_AREA_REGISTRY_LABEL_UPDATED,
            EventAreaRegistryLabelUpdatedData(),
        )

    @callback
    def _data_to_save(self) -> old_ar.AreasRegistryStoreData:
        """Return data of area registry to store in a file."""
        result = super()._data_to_save()

        view = self.areas.view
        for area in result["areas"]:
            area_entry = view[area["id"]]
            area["floor_id"] = area_entry.shadow_floor_id
            area["labels"] = list(area_entry.shadow_labels)

        return result


@callback
@singleton(DATA_REGISTRY)
def async_get(hass: HomeAssistant) -> AreaRegistry:
    """Get device registry."""
    old_registry = old_ar.async_get(hass)
    return AreaRegistry(hass, old_registry)


@callback
def async_load(hass: HomeAssistant) -> None:
    """Load device registry."""
    assert DATA_REGISTRY not in hass.data
    async_get(hass).async_load_cb()
    old_ar.async_get = async_get


@callback
def _async_setup_labels(hass: HomeAssistant, registry: AreaRegistry) -> None:
    """Clean up entities caches when labels ancestry updated."""

    @callback
    def _handle_label_registry_extra_update(
        event: lr.EventLabelRegistryExtraUpdated,
    ) -> None:
        registry.async_update_label_areas()

    hass.bus.async_listen(
        event_type=lr.EVENT_LABEL_REGISTRY_EXTRA_UPDATED,
        listener=_handle_label_registry_extra_update,
    )
