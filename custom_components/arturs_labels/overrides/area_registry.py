"""Provide a registry for areas."""

from __future__ import annotations

from collections.abc import Mapping
import dataclasses
from dataclasses import dataclass
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as old_ar  # noqa: ICN001
from homeassistant.helpers.singleton import singleton
from homeassistant.util.hass_dict import HassKey

_LOGGER = logging.getLogger(__name__)

DATA_REGISTRY: HassKey[AreaRegistry] = HassKey("arturs_area_registry")

NULL_LABELS: set[str] = set()


@dataclass(frozen=True, kw_only=True)
class AreaEntry(old_ar.AreaEntry):
    """Area Registry Entry."""

    shadow_labels: set[str]


class AreaRegistryItems(old_ar.AreaRegistryItems):
    """Container for active area registry items, maps area id -> entry."""

    view: Mapping[str, AreaEntry]

    def __init__(self) -> None:
        """Initialize the container."""
        super().__init__()
        self.view = self.data  # type: ignore [assignment]

    def _index_entry(self, key: str, entry: old_ar.AreaEntry) -> None:
        """Index an entry."""
        if type(entry) is not AreaEntry:
            entry_dict = dataclasses.asdict(entry)
            entry_dict["labels"] = NULL_LABELS

            entry = AreaEntry(**entry_dict, shadow_labels=entry.labels)
            self.data[key] = entry

        super()._index_entry(key, entry)


class AreaRegistry(old_ar.AreaRegistry):
    """Class to hold a registry of devices."""

    areas: AreaRegistryItems

    _old_registry: old_ar.AreaRegistry

    def __init__(self, hass: HomeAssistant, old_registry: old_ar.AreaRegistry) -> None:
        """Initialize the device registry."""
        # pylint: disable=super-init-not-called
        self.hass = hass
        self._old_registry = old_registry
        self._store = old_registry._store  # noqa: SLF001

    @callback
    def async_create(self, *args, labels=None, **kwargs) -> old_ar.AreaEntry:
        """Create a new area."""
        return super().async_create(*args, **kwargs)

    @callback
    def _async_update(self, *args, labels=None, **kwargs) -> old_ar.AreaEntry:
        """Update properties of an area."""
        return super()._async_update(*args, **kwargs)

    async def async_load(self) -> None:
        """Erase method."""
        raise NotImplementedError

    @callback
    def async_load_cb(self) -> None:
        """Load the area registry."""
        areas = AreaRegistryItems()
        areas.update(self._old_registry.areas)

        self.areas = areas
        self._area_data = areas.data

        self._old_registry.areas = self.areas
        self._old_registry._area_data = self._area_data  # noqa: SLF001
        self._old_registry.__class__ = self.__class__

    @callback
    def _data_to_save(self) -> old_ar.AreasRegistryStoreData:
        """Return data of area registry to store in a file."""
        result = super()._data_to_save()

        view = self.areas.view
        for area in result["areas"]:
            area["labels"] = list(view[area["id"]].shadow_labels)

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
