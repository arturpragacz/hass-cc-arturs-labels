"""Provide a registry base."""

from typing import TYPE_CHECKING, Any

import attr

from homeassistant.core import callback

from ..utils import add_assign_label_id
from . import label_registry as lr

if TYPE_CHECKING:
    # mypy cannot workout _cache Protocol with attrs
    from propcache.api import cached_property as under_cached_property
else:
    from propcache.api import under_cached_property

NULL_AREA: None = None


class RegistryEntryBaseMeta(type):
    """Registry Entry Base metaclass.

    This fixes TypeError: multiple bases have instance lay-out conflict.
    This problem is generated when multiple bases have non-empty slots.
    """

    collected_attrs: dict[str, Any] | None = None

    def __new__(mcs, name, bases, attrs):  # noqa: N804
        """Create new Registry Entry class."""
        if name == "RegistryEntryBase":
            if mcs.collected_attrs is None:
                mcs.collected_attrs = attrs

        elif bases and bases[0] is RegistryEntryBase:
            derive_types = bases[1:]

            @attr.s(slots=True, frozen=True, kw_only=True)
            class RegistryEntryBaseDerived(*derive_types):
                vars().update(mcs.collected_attrs)

            bases = (RegistryEntryBaseDerived,)

        return super().__new__(mcs, name, bases, attrs)


@attr.s(slots=True, frozen=True, kw_only=True)
class RegistryEntryBase(metaclass=RegistryEntryBaseMeta):
    """Registry Entry Base for entities and devices."""

    labels: set[str] = attr.ib(factory=set)
    ancestry_labels: set[str] = attr.ib(factory=set)
    effective_labels: set[str] = attr.ib(factory=set)
    extra_labels_init: bool = attr.ib(default=True)

    area_id: str | None = attr.ib(init=False, default=NULL_AREA)
    shadow_area_id: str | None = attr.ib(alias="area_id", default=None)

    _cache: dict[str, Any] = attr.ib(factory=dict, eq=False, init=False)

    def set_extra_labels_init(self, value: bool = True) -> None:
        """Set effective labels init."""
        object.__setattr__(self, "extra_labels_init", value)

    @under_cached_property
    def _frontend_labels(self) -> list[str]:
        labels = list(self.effective_labels)
        labels += [add_assign_label_id(label_id) for label_id in self.labels]
        return labels

    def set_area_id_shadow(self, shadow: bool) -> None:
        """Set area_id."""
        if shadow:
            object.__setattr__(self, "area_id", NULL_AREA)
        else:
            object.__setattr__(self, "area_id", self.shadow_area_id)


@callback
def async_get_ancestry_labels(
    lab_reg: lr.LabelRegistry, assigned_labels: set[str]
) -> set[str]:
    """Get ancestry labels. Includes self."""
    return lab_reg.async_get_ancestors(assigned_labels)


@callback
def async_get_effective_labels(
    lab_reg: lr.LabelRegistry, ancestry_labels: set[str]
) -> set[str]:
    """Get effective labels."""

    def label(label_id: str) -> bool:
        return label_id in ancestry_labels

    glbls = {"__builtins__": None, "label": label}
    lcls: dict[str, Any] = {}

    effective_labels = ancestry_labels.copy()

    for label_id, code in lab_reg.label_rules.items():
        try:
            result = eval(code, glbls, lcls)  # noqa: S307
        except Exception:  # noqa: BLE001
            continue

        if result:
            effective_labels.add(label_id)

    return effective_labels
