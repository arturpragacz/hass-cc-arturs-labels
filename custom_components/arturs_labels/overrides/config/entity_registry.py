"""Websocket API to interact with the entity registry."""

import logging
from typing import Any

from homeassistant.components.config import entity_registry as old_m
import homeassistant.components.websocket_api as api
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant, callback

from ..utils import remove_assign_label_id
from .utils import async_setup as async_setup_template

_LOGGER = logging.getLogger(__name__)

old_mod: dict[str, api.WebSocketCommandHandler] = {}


@callback
def async_setup(hass: HomeAssistant) -> bool:
    """Set up the Entity Registry WS commands."""
    async_setup_template(
        old_m,
        old_mod,
        (("websocket_update_entity", websocket_update_entity),),
    )
    return True


@callback
def websocket_update_entity(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Update entity command."""
    raw_labels = msg.get("labels")
    if raw_labels is not None:
        labels = []
        for raw_label_id in raw_labels:
            label_id = remove_assign_label_id(raw_label_id)
            if label_id is not None:
                labels.append(label_id)

        msg["labels"] = labels

    old_mod["websocket_update_entity"](hass, connection, msg)
