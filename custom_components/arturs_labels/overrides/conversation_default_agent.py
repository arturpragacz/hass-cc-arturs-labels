"""Standard conversation implementation for Home Assistant."""

from collections.abc import Callable
from typing import TypedDict

from hassil.intents import SlotList

from homeassistant.components.conversation.default_agent import (
    DefaultAgent as OldDefaultAgent,
    TextSlotList,
)
from homeassistant.core import HomeAssistant, callback

from . import area_registry as ar, device_registry as dr, label_registry as lr


class _OldDefaultAgent(TypedDict, total=False):
    make_slot_lists: Callable[[OldDefaultAgent], dict[str, SlotList]]
    get_device_area: Callable[[OldDefaultAgent, str | None], ar.OldAreaEntry | None]
    listen_clear_slot_list: Callable[[OldDefaultAgent], None]


old_default_agent: _OldDefaultAgent = _OldDefaultAgent()


@callback
def async_setup(hass: HomeAssistant) -> bool:
    """Set up the services helper."""
    old_default_agent["make_slot_lists"] = OldDefaultAgent._make_slot_lists  # noqa: SLF001
    old_default_agent["get_device_area"] = OldDefaultAgent._get_device_area  # noqa: SLF001
    old_default_agent["listen_clear_slot_list"] = (
        OldDefaultAgent._listen_clear_slot_list  # noqa: SLF001
    )

    OldDefaultAgent._make_slot_lists = make_slot_lists  # type: ignore [method-assign] # noqa: SLF001
    OldDefaultAgent._get_device_area = get_device_area  # type: ignore [method-assign] # noqa: SLF001
    OldDefaultAgent._listen_clear_slot_list = listen_clear_slot_list  # type: ignore [method-assign] # noqa: SLF001

    return True


@callback
def make_slot_lists(self: OldDefaultAgent) -> dict[str, SlotList]:
    """Create slot lists with areas and entity names/aliases."""
    if self._slot_lists is not None:
        return self._slot_lists

    assert "make_slot_lists" in old_default_agent
    slot_lists = old_default_agent["make_slot_lists"](self)

    # Expose all areas.
    area_reg = ar.async_get(self.hass)
    area_names = []
    for area in area_reg.async_list_areas(active=True):
        area_names.append((area.name, area.name))
        if not area.aliases:
            continue

        for alias in area.aliases:
            alias = alias.strip()
            if not alias:
                continue

            area_names.append((alias, alias))

    slot_lists["area"] = TextSlotList.from_tuples(area_names, allow_template=False)

    return slot_lists


@callback
def listen_clear_slot_list(self: OldDefaultAgent) -> None:
    """Listen for changes that can invalidate slot list."""
    assert "listen_clear_slot_list" in old_default_agent
    old_default_agent["listen_clear_slot_list"](self)

    assert self._unsub_clear_slot_list is not None
    self._unsub_clear_slot_list.append(
        self.hass.bus.async_listen(
            ar.EVENT_AREA_REGISTRY_LABEL_UPDATED,
            self._async_clear_slot_list,
        )
    )


def get_device_area(
    self: OldDefaultAgent, device_id: str | None
) -> ar.OldAreaEntry | None:
    """Return area object for given device identifier."""
    if device_id is None:
        return None

    dev_reg = dr.async_get(self.hass)
    device = dev_reg.async_get(device_id)
    if device is None:
        return None

    lab_reg = lr.async_get(self.hass)

    # ultimately we want to use the responsibility area
    # before that maybe main area (defaulted to smallest area)
    areas = device.labels & lab_reg.areas
    if not areas:
        return None

    area_id = next(iter(areas))
    area_reg = ar.async_get(self.hass)
    return area_reg.async_get_area(area_id)
