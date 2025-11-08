"""Entity target related helpers."""

from collections.abc import Callable

from homeassistant.components import homeassistant as homeassistant_component
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.target as old_target
from homeassistant.helpers.target import SelectedEntities, TargetSelectorData

from .registry import device_registry as dr

old_func: (
    Callable[[HomeAssistant, TargetSelectorData, bool], SelectedEntities] | None
) = None


@callback
def async_setup(hass: HomeAssistant) -> bool:
    """Set up the target helper."""
    global old_func  # pylint: disable=global-statement # noqa: PLW0603
    old_func = old_target.async_extract_referenced_entity_ids
    old_target.async_extract_referenced_entity_ids = async_extract_referenced_entity_ids
    homeassistant_component.async_extract_referenced_entity_ids = (
        async_extract_referenced_entity_ids
    )
    return True


def async_extract_referenced_entity_ids(
    hass: HomeAssistant, selector_data: TargetSelectorData, *args, **kwargs
) -> SelectedEntities:
    """Extract referenced entity IDs from a service call."""
    dev_reg = dr.async_get(hass)

    assert old_func
    dev_reg.devices.no_devices_for_label = True
    try:
        result = old_func(hass, selector_data, *args, **kwargs)
    finally:
        dev_reg.devices.no_devices_for_label = False

    for label_id in selector_data.label_ids:
        for device_entry in dev_reg.devices.get_devices_for_label(label_id):
            result.referenced_devices.add(device_entry.id)

    return result
