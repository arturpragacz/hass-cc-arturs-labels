"""Provide a registry base."""

from typing import TYPE_CHECKING

import attr

from homeassistant.core import callback

from . import label_registry as lr
from .utils import add_assign_label_id

if TYPE_CHECKING:
    # mypy cannot workout _cache Protocol with attrs
    from propcache import cached_property as under_cached_property
else:
    from propcache import under_cached_property

NULL_AREA: None = None


@attr.s(frozen=True, kw_only=True)
class RegistryEntryBase:
    """Registry Entry Base for entities and devices."""

    labels: set[str] = attr.ib(factory=set)
    effective_labels: set[str] = attr.ib(factory=set)
    extra_labels_init: bool = attr.ib(default=True)

    area_id: str | None = attr.ib(init=False, default=NULL_AREA)
    shadow_area_id: str | None = attr.ib(alias="area_id", default=None)

    def set_extra_labels_init(self, value: bool = True) -> None:
        """Set effective labels init."""
        self.__dict__["extra_labels_init"] = value

    @under_cached_property
    def _frontend_labels(self) -> list[str]:
        labels = list(self.effective_labels)
        labels += [add_assign_label_id(label_id) for label_id in self.labels]
        return labels

    def set_area_id_shadow(self, shadow: bool) -> None:
        """Set area_id."""
        if shadow:
            self.__dict__["area_id"] = NULL_AREA
        else:
            self.__dict__["area_id"] = self.shadow_area_id


@callback
def async_get_effective_labels(
    lab_reg: lr.LabelRegistry, assigned_labels: set[str]
) -> set[str]:
    """Get effective labels."""
    return lab_reg.async_get_ancestors(assigned_labels)
