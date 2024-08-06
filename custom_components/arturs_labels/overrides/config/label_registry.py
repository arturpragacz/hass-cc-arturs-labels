"""Websocket API to interact with the label registry."""

import logging
from typing import Any

import homeassistant.components.config.label_registry as old_m
import homeassistant.components.websocket_api as api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.core import HomeAssistant, callback

from .. import label_registry as lr
from ..utils import add_assign_label_id, add_assign_label_name
from .utils import async_setup as async_setup_template

_LOGGER = logging.getLogger(__name__)

old_mod: dict[str, api.WebSocketCommandHandler] = {}


@callback
def async_setup(hass: HomeAssistant) -> bool:
    """Set up the Label Registry WS commands."""
    async_setup_template(
        old_m,
        old_mod,
        (
            ("websocket_list_labels", websocket_list_labels),
            ("websocket_create_label", websocket_create_label),
            ("websocket_delete_label", websocket_delete_label),
            ("websocket_update_label", websocket_update_label),
        ),
    )
    return True


@callback
def websocket_list_labels(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """List labels command."""
    registry = lr.async_get(hass)

    labels = [old_m._entry_dict(entry) for entry in registry.async_list_labels()]  # noqa: SLF001
    assign_labels = []
    for label in labels:
        assign_label = label.copy()
        assign_label["label_id"] = add_assign_label_id(assign_label["label_id"])
        assign_label["name"] = add_assign_label_name(assign_label["name"])
        assign_labels.append(assign_label)

        label["name"] = " " + label["name"]

    labels += assign_labels

    connection.send_result(msg["id"], labels)


@callback
def websocket_create_label(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Create label command."""
    name = msg["name"]
    if ":" in name:
        connection.send_error(msg["id"], "invalid_info", "Cannot create special label")
        return

    old_mod["websocket_create_label"](hass, connection, msg)


@callback
def websocket_delete_label(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Delete label command."""
    label_id = msg["label_id"]
    if ":" in label_id:
        connection.send_error(msg["id"], "invalid_info", "Cannot delete special label")
        return

    old_mod["websocket_delete_label"](hass, connection, msg)


@callback
def websocket_update_label(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Update label command."""
    label_id = msg["label_id"]
    if ":" in label_id:
        connection.send_error(msg["id"], "invalid_info", "Cannot update special label")
        return

    name = msg.get("name")
    if name is not None and ":" in name:
        connection.send_error(msg["id"], "invalid_info", "Cannot create special label")
        return

    old_mod["websocket_update_label"](hass, connection, msg)
