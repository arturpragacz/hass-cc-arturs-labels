"""Config Override utilities."""

from collections.abc import Iterable
from types import ModuleType

import homeassistant.components.websocket_api as api


def async_setup(
    old_m: ModuleType,
    old_mod: dict[str, api.WebSocketCommandHandler],
    replacements: Iterable[tuple[str, api.WebSocketCommandHandler]],
) -> bool:
    """Set up the Entity Registry WS commands."""
    for name, new in replacements:
        old = old_mod[name] = getattr(old_m, name)
        new._ws_command = old._ws_command  # type: ignore[attr-defined] # noqa: SLF001
        new._ws_schema = old._ws_schema  # type: ignore[attr-defined] # noqa: SLF001
        setattr(old_m, name, new)
    return True
