"""The methods for loading Home Assistant integrations."""

from collections.abc import Callable

from homeassistant.core import HomeAssistant, ServiceCall, callback
import homeassistant.helpers.service as old_service
from homeassistant.helpers.service import SelectedEntities, ServiceTargetSelector
from homeassistant.loader import bind_hass

from . import device_registry as dr

old_func: Callable[[HomeAssistant, ServiceCall, bool], SelectedEntities] | None = None


@callback
def async_setup(hass: HomeAssistant) -> bool:
    """Set up the services helper."""
    global old_func  # pylint: disable=global-statement # noqa: PLW0603
    old_func = old_service.async_extract_referenced_entity_ids
    old_service.async_extract_referenced_entity_ids = (
        async_extract_referenced_entity_ids
    )
    return True


@bind_hass
def async_extract_referenced_entity_ids(
    hass: HomeAssistant, service_call: ServiceCall, *args, **kwargs
) -> SelectedEntities:
    """Extract referenced entity IDs from a service call."""
    dev_reg = dr.async_get(hass)

    dev_reg.devices.no_devices_for_label = True
    assert old_func
    try:
        result = old_func(hass, service_call, *args, **kwargs)
    finally:
        dev_reg.devices.no_devices_for_label = False

    selector = ServiceTargetSelector(service_call)
    if selector.label_ids:
        for label_id in selector.label_ids:
            for device_entry in dev_reg.devices.get_devices_for_label(label_id):
                result.referenced_devices.add(device_entry.id)

    return result
