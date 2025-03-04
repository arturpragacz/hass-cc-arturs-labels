"""User intents related helpers."""

from collections.abc import Callable, Collection, Iterable
from typing import Protocol, TypedDict, cast

from homeassistant.core import HomeAssistant, State, callback
import homeassistant.helpers.intent as old_m
from homeassistant.helpers.intent import (
    MatchTargetsCandidate,
    MatchTargetsConstraints,
    MatchTargetsPreferences,
    MatchTargetsResult,
)

from .registry import area_registry as ar, entity_registry as er


class _AsyncMatchTargets(Protocol):
    def __call__(
        self,
        hass: HomeAssistant,
        constraints: MatchTargetsConstraints,
        preferences: MatchTargetsPreferences | None = None,
        states: list[State] | None = None,
        area_candidate_filter: Callable[
            [MatchTargetsCandidate, Collection[str]], bool
        ] = ...,
    ) -> MatchTargetsResult: ...


class _OldMod(TypedDict, total=False):
    async_match_targets: _AsyncMatchTargets
    find_areas: Callable[[str, ar.AreaRegistry], Iterable[ar.OldAreaEntry]]


old_mod: _OldMod = _OldMod()


@callback
def async_setup(hass: HomeAssistant) -> bool:
    """Set up the services helper."""
    old_mod["find_areas"] = old_m.find_areas
    old_mod["async_match_targets"] = old_m.async_match_targets

    old_m.find_areas = find_areas
    old_m.async_match_targets = async_match_targets

    return True


def find_areas(name: str, areas: ar.old_ar.AreaRegistry) -> Iterable[ar.OldAreaEntry]:
    """Find all areas matching a name (including aliases)."""
    areas = cast(ar.AreaRegistry, areas)

    _normalize_name = old_m._normalize_name  # noqa: SLF001
    name_norm = _normalize_name(name)
    for area in areas.async_list_areas(active=True):
        # Accept name or area id
        if (area.id == name) or (_normalize_name(area.name) == name_norm):
            yield area
            continue

        if not area.aliases:
            continue

        for alias in area.aliases:
            if _normalize_name(alias) == name_norm:
                yield area
                break


def _default_area_candidate_filter(
    candidate: MatchTargetsCandidate, possible_area_ids: Collection[str]
) -> bool:
    """Keep candidates in the possible areas."""
    entity = cast(er.RegistryEntry | None, candidate.entity)

    return entity is not None and not entity.effective_labels.isdisjoint(
        possible_area_ids
    )


@callback
def async_match_targets(
    hass: HomeAssistant,
    constraints: MatchTargetsConstraints,
    preferences: MatchTargetsPreferences | None = None,
    states: list[State] | None = None,
    area_candidate_filter: Callable[
        [MatchTargetsCandidate, Collection[str]], bool
    ] = _default_area_candidate_filter,
) -> MatchTargetsResult:
    """Match entities based on constraints in order to handle an intent."""
    constraints.floor_name = None
    preferences = preferences or MatchTargetsPreferences()
    preferences.floor_id = None
    return old_mod["async_match_targets"](
        hass,
        constraints,
        preferences,
        states,
        area_candidate_filter=area_candidate_filter,
    )
