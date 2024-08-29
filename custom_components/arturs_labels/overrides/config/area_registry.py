"""Websocket API to interact with the area registry."""

import logging
from typing import Any

import homeassistant.components.config.area_registry as old_m
import homeassistant.components.websocket_api as api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.core import HomeAssistant, callback

from .. import area_registry as ar
from .utils import async_setup as async_setup_template

_LOGGER = logging.getLogger(__name__)

old_mod: dict[str, api.WebSocketCommandHandler] = {}


@callback
def async_setup(hass: HomeAssistant) -> bool:
    """Set up the Label Registry WS commands."""
    async_setup_template(
        old_m,
        old_mod,
        (("websocket_list_areas", websocket_list_areas),),
    )
    return True


@callback
def websocket_list_areas(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """List areas command."""
    registry = ar.async_get(hass)

    areas = {
        entry.id: entry.json_fragment
        for entry in registry.async_list_areas(active=True)
    }
    for entry in registry.async_list_areas():
        areas.setdefault(entry.id, entry.json_fragment)

    connection.send_result(
        msg["id"],
        list(areas.values()),
    )
