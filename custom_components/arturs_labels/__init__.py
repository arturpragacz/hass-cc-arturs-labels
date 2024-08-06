"""Artur's labels component."""

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
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

    dr.async_load(hass)
    er.async_load(hass)
    ar.async_load(hass)

    con_lr.async_setup(hass)
    con_dr.async_setup(hass)
    con_er.async_setup(hass)

    return True
