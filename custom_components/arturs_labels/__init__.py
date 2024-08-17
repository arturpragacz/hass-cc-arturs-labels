"""Artur's labels component."""

import logging

import voluptuous as vol

from homeassistant.const import SERVICE_RELOAD
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType

from .overrides import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    label_registry as lr,
    service as service_helper,
)
from .overrides.config import (
    device_registry as con_dr,
    entity_registry as con_er,
    label_registry as con_lr,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "arturs_labels"

LABEL_SCHEMA = {
    str: {
        vol.Required("parents", default=[]): vol.All(
            cv.ensure_list, [str], vol.util.Set()
        ),
    },
}

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(DOMAIN): {
            vol.Required("labels", default=[]): LABEL_SCHEMA,
        },
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the arturs_labels component."""
    labels_parents = {}
    for label_id, label_data in config[DOMAIN]["labels"].items():
        labels_parents[label_id] = label_data["parents"]

    service_helper.async_setup(hass)

    # lr has to be loaded first, because others depend on it
    lr.async_load(hass, labels_parents)

    # dr has to be loaded before er, so that callbacks
    # to lr.EVENT_LABEL_REGISTRY_ANCESTRY_UPDATED fire in correct order
    dr.async_load(hass)

    er.async_load(hass)
    ar.async_load(hass)

    con_lr.async_setup(hass)
    con_dr.async_setup(hass)
    con_er.async_setup(hass)

    async def _handle_reload(service_call: ServiceCall) -> None:
        await async_reload(hass)
        hass.bus.async_fire(f"event_{DOMAIN}_reloaded", context=service_call.context)

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_RELOAD,
        _handle_reload,
    )

    return True


async def async_reload(hass: HomeAssistant) -> None:
    """Reload component."""
    config = await async_integration_yaml_config(hass, DOMAIN)

    if config is None or DOMAIN not in config:
        return

    labels_parents = {}
    for label_id, label_data in config[DOMAIN]["labels"].items():
        labels_parents[label_id] = label_data["parents"]

    lab_reg = lr.async_get(hass)
    lab_reg.async_load_parents(labels_parents)
