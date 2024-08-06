"""Provide a registry for labels."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import dataclasses
from dataclasses import dataclass, field
import logging
from typing import Any, TypedDict

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import label_registry as old_lr  # noqa: ICN001
from homeassistant.helpers.normalized_name_base_registry import (
    NormalizedNameBaseRegistryItems,
)
from homeassistant.helpers.singleton import singleton
from homeassistant.util.event_type import EventType
from homeassistant.util.hass_dict import HassKey

_LOGGER = logging.getLogger(__name__)

DATA_REGISTRY: HassKey[LabelRegistry] = HassKey("arturs_label_registry")

EVENT_LABEL_REGISTRY_ANCESTRY_UPDATED: EventType[
    EventLabelRegistryAncestryUpdatedData
] = EventType("arturs_label_registry_ancestry_updated")


class EventLabelRegistryAncestryUpdatedData(TypedDict):
    """Event data for when the label ancestry is updated."""


type EventLabelRegistryAncestryUpdated = Event[EventLabelRegistryAncestryUpdatedData]


@dataclass(slots=True, frozen=True, kw_only=True)
class LabelEntry(old_lr.LabelEntry):
    """Label Registry Entry."""

    mut: dict = field(
        default_factory=lambda: {
            "parents": None,  # : set[str] | None; does not include self; can be None
            "ancestors": None,  # : set[str] | None; includes self, if not None; can be None
            "equivalents": None,  # : set[str] | None; includes self, if not None; can be None
        }
    )

    @property
    def parents(self) -> set[str] | None:
        """Parents."""
        return self.mut["parents"]

    @property
    def ancestors(self) -> set[str] | None:
        """Ancestors."""
        return self.mut["ancestors"]

    @property
    def equivalents(self) -> set[str] | None:
        """Equivalents."""
        return self.mut["equivalents"]


def _is_label_special(label_id: str) -> bool:
    return ":" in label_id


class LabelRegistryItems(NormalizedNameBaseRegistryItems[old_lr.LabelEntry]):
    """Container for label registry items, maps label_id -> entry."""

    view: Mapping[str, LabelEntry]

    def __init__(self) -> None:
        """Initialize the container."""
        super().__init__()
        self.view = self.data  # type: ignore [assignment]

    def _index_entry(self, key: str, entry: old_lr.LabelEntry) -> None:
        """Index an entry."""
        if type(entry) is not LabelEntry:
            entry = self.data[key] = LabelEntry(**dataclasses.asdict(entry))

        super()._index_entry(key, entry)


class LabelRegistry(old_lr.LabelRegistry):
    """Class to hold a registry of labels."""

    labels: LabelRegistryItems

    _old_registry: old_lr.LabelRegistry
    _parents: dict[str, set[str]]

    def __init__(self, hass: HomeAssistant, old_registry: old_lr.LabelRegistry) -> None:
        """Initialize the label registry."""
        # pylint: disable=super-init-not-called
        self.hass = hass
        self._old_registry = old_registry
        self._store = old_registry._store  # noqa: SLF001

    @callback
    def async_create(self, *args, **kwargs) -> old_lr.LabelEntry:
        """Create a new label."""
        label = super().async_create(*args, **kwargs)
        self._async_compute_ancestry()
        return label

    @callback
    def async_delete(self, label_id: str) -> None:
        """Delete label."""
        super().async_delete(label_id)
        self._async_compute_ancestry()

    async def async_load(self) -> None:
        """Erase method."""
        raise NotImplementedError

    @callback
    def async_load_cb(self) -> None:
        """Load the label registry."""
        labels = LabelRegistryItems()
        labels.update(self._old_registry.labels)

        self.labels = labels
        self._label_data = labels.data

        self._old_registry.labels = self.labels
        self._old_registry._label_data = self._label_data  # noqa: SLF001
        self._old_registry.__class__ = self.__class__

    @callback
    def async_load_parents(
        self, labels_parents: dict[str, set[str]], *, fire: bool = True
    ):
        """Load the labels ancestry."""
        labels_parents = {
            item[0]: item[1]
            for item in labels_parents.items()
            if not _is_label_special(item[0])
        }
        for label_id, parents in labels_parents.items():
            parents.discard(label_id)
            discards = [parent for parent in parents if _is_label_special(parent)]
            parents.difference_update(discards)

        self._parents = labels_parents
        self._async_compute_ancestry(fire=fire)

    def _async_compute_ancestry(self, *, fire: bool = True) -> None:
        all_label_ids = self.labels.keys()
        for label in self.labels.view.values():
            label.mut["ancestors"] = None
            parents = self._parents.get(label.label_id, None)
            if parents is None:
                label.mut["parents"] = None
            else:
                real_parents = parents & all_label_ids
                label.mut["parents"] = real_parents

        self._async_do_compute_ancestry()

        if fire:
            self.hass.bus.async_fire(
                EVENT_LABEL_REGISTRY_ANCESTRY_UPDATED,
                EventLabelRegistryAncestryUpdatedData(),
            )

    def _async_do_compute_ancestry(self) -> None:
        indices: dict[str, int] = {}
        for label_id in self.labels:
            indices[label_id] = -1

        count = 0
        equivalents_stack: list[str] = []

        def compute_ancestry_impl(label: LabelEntry) -> int | None:
            """Compute ancestry and return encountered cycles.

            Uses DFS and modified Tarjan's strongly connected components algorithm.

            index == -1 -> not visited
            index > 0   -> visiting
            index == 0  -> visited

            result = 0       -> prev visited
            result = index   -> prev visiting
            result = lowlink -> normal recurse
            """
            label_id = label.label_id

            index = indices[label_id]
            if index >= 0:  # either already visited or a cycle
                return index

            nonlocal count, equivalents_stack
            count += 1
            index = indices[label_id] = count
            stack_index = len(equivalents_stack)

            parents = label.parents
            ancestors: set[str] = set()
            lowlink = index
            if parents is not None:
                for parent_id in parents:
                    parent = self.labels.view[parent_id]
                    result = compute_ancestry_impl(parent)

                    if parent.ancestors is not None:
                        ancestors |= parent.ancestors
                    else:
                        ancestors.add(parent_id)

                    if result:
                        lowlink = min(lowlink, result)

            if ancestors:
                ancestors.add(label_id)
                label.mut["ancestors"] = ancestors

            if index == lowlink:  # a root node, marks the boundary of SCC
                if len(equivalents_stack) > stack_index:
                    equivalents = set(equivalents_stack[stack_index:])
                    for equivalent_id in equivalents:
                        equivalent = self.labels.view[equivalent_id]
                        equivalent.mut["ancestors"] = ancestors
                        equivalent.mut["equivalents"] = equivalents

                    equivalents.add(label_id)
                    label.mut["equivalents"] = equivalents

                    del equivalents_stack[stack_index:]
            else:
                equivalents_stack.append(label_id)

            indices[label_id] = 0

            return lowlink

        for label_id, index in indices.items():
            if index:
                label = self.labels.view[label_id]
                compute_ancestry_impl(label)

    @callback
    def async_get_ancestors(self, label_ids: Iterable[str]) -> set[str]:
        """Get labels' ancestors."""
        ancestors = set()

        for label_id in label_ids:
            label = self.labels.view.get(label_id)
            if label is not None:
                if label.ancestors is not None:
                    ancestors |= label.ancestors
                else:
                    ancestors.add(label_id)

        # label may have been removed, but ancestry not yet recalculated
        # so let's remove the bad labels here to have some form of consistency in output
        all_label_ids = self.labels.keys()
        ancestors &= all_label_ids

        return ancestors


@callback
@singleton(DATA_REGISTRY)
def async_get(hass: HomeAssistant) -> LabelRegistry:
    """Get label registry."""
    old_registry = old_lr.async_get(hass)
    return LabelRegistry(hass, old_registry)


@callback
def async_load(hass: HomeAssistant, labels_parents: dict[str, Any]) -> None:
    """Load label registry."""
    assert DATA_REGISTRY not in hass.data
    registry = async_get(hass)
    registry.async_load_cb()
    registry.async_load_parents(labels_parents, fire=False)
    old_lr.async_get = async_get
