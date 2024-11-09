"""User intents related helpers."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import groupby
from typing import TypedDict, cast

from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.core import HomeAssistant, State, callback
import homeassistant.helpers.intent as old_m
from homeassistant.helpers.intent import (
    MatchFailedReason,
    MatchTargetsCandidate as OldMatchTargetsCandidate,
    MatchTargetsConstraints,
    MatchTargetsPreferences,
    MatchTargetsResult,
)

from . import area_registry as ar, entity_registry as er


class _OldMod(TypedDict, total=False):
    async_match_targets: Callable[
        [
            HomeAssistant,
            MatchTargetsConstraints,
            MatchTargetsPreferences | None,
            list[State] | None,
        ],
        MatchTargetsResult,
    ]


old_mod: _OldMod = _OldMod()


@callback
def async_setup(hass: HomeAssistant) -> bool:
    """Set up the services helper."""
    old_mod["async_match_targets"] = old_m.async_match_targets
    old_m.async_match_targets = async_match_targets

    return True


@dataclass
class MatchTargetsCandidate(OldMatchTargetsCandidate):
    """Candidate for async_match_targets."""

    entity: er.RegistryEntry | None = None


def _filter_by_name(
    name: str,
    candidates: Iterable[MatchTargetsCandidate],
) -> Iterable[MatchTargetsCandidate]:
    """Filter candidates by name."""
    result = old_m._filter_by_name(name, candidates)  # noqa: SLF001
    return cast(Iterable[MatchTargetsCandidate], result)


def _filter_by_features(
    features: int,
    candidates: Iterable[MatchTargetsCandidate],
) -> Iterable[MatchTargetsCandidate]:
    """Filter candidates by supported features."""
    result = old_m._filter_by_features(features, candidates)  # noqa: SLF001
    return cast(Iterable[MatchTargetsCandidate], result)


def _filter_by_device_classes(
    device_classes: Iterable[str],
    candidates: Iterable[MatchTargetsCandidate],
) -> Iterable[MatchTargetsCandidate]:
    """Filter candidates by device classes."""
    result = old_m._filter_by_device_classes(device_classes, candidates)  # noqa: SLF001
    return cast(Iterable[MatchTargetsCandidate], result)


def _find_areas(name: str, areas: ar.AreaRegistry) -> Iterable[ar.OldAreaEntry]:
    """Find all areas matching a name (including aliases)."""
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


def _async_match_areas_assistant_and_duplicates(
    hass: HomeAssistant,
    constraints: MatchTargetsConstraints,
    preferences: MatchTargetsPreferences,
    candidates: list[MatchTargetsCandidate],
) -> tuple[
    list[MatchTargetsCandidate], list[ar.OldAreaEntry] | None, MatchTargetsResult | None
]:
    targeted_areas: list[ar.OldAreaEntry] | None = None

    def return_func(
        match_result: MatchTargetsResult | None,
    ) -> tuple[
        list[MatchTargetsCandidate],
        list[ar.OldAreaEntry] | None,
        MatchTargetsResult | None,
    ]:
        return candidates, targeted_areas, match_result

    if constraints.area_name:
        area_reg = ar.async_get(hass)

        targeted_areas = list(_find_areas(constraints.area_name, area_reg))
        if not targeted_areas:
            return return_func(
                MatchTargetsResult(
                    False,
                    MatchFailedReason.INVALID_AREA,
                    no_match_name=constraints.area_name,
                )
            )
        targeted_area_ids = {area.id for area in targeted_areas}

        candidates = [
            c
            for c in candidates
            if c.entity is not None
            and not c.entity.effective_labels.isdisjoint(targeted_area_ids)
        ]
        if not candidates:
            return return_func(
                MatchTargetsResult(False, MatchFailedReason.AREA, areas=targeted_areas)
            )

    if constraints.assistant:
        # Check exposure
        candidates = [c for c in candidates if c.is_exposed]
        if not candidates:
            return return_func(MatchTargetsResult(False, MatchFailedReason.ASSISTANT))

    if constraints.name and (not constraints.allow_duplicate_names):
        # Check for duplicates
        sorted_candidates = sorted(
            [c for c in candidates if c.matched_name],
            key=lambda c: c.matched_name or "",
        )

        final_candidates: list[MatchTargetsCandidate] = []
        for name, group in groupby(sorted_candidates, key=lambda c: c.matched_name):
            group_candidates = list(group)
            if len(group_candidates) < 2:
                # No duplicates for name
                final_candidates.extend(group_candidates)
                continue

            # Try to disambiguate by preferences
            if preferences.area_id:
                group_candidates = [
                    c
                    for c in group_candidates
                    if c.entity is not None
                    and preferences.area_id in c.entity.effective_labels
                ]
                if len(group_candidates) < 2:
                    # Disambiguated by area
                    final_candidates.extend(group_candidates)
                    continue

            # Couldn't disambiguate duplicate names
            return return_func(
                MatchTargetsResult(
                    False,
                    MatchFailedReason.DUPLICATE_NAME,
                    no_match_name=name,
                    areas=targeted_areas or [],
                )
            )

        candidates = final_candidates

        if not final_candidates:
            return return_func(
                MatchTargetsResult(
                    False,
                    MatchFailedReason.NAME,
                    areas=targeted_areas or [],
                )
            )

    return return_func(None)


@callback
def async_match_targets(
    hass: HomeAssistant,
    constraints: MatchTargetsConstraints,
    preferences: MatchTargetsPreferences | None = None,
    states: list[State] | None = None,
) -> MatchTargetsResult:
    """Match entities based on constraints in order to handle an intent."""
    preferences = preferences or MatchTargetsPreferences()
    filtered_by_domain = False

    if not states:
        # Get all states and filter by domain
        states = hass.states.async_all(constraints.domains)
        filtered_by_domain = True
        if not states:
            return MatchTargetsResult(False, MatchFailedReason.DOMAIN)

    candidates = [
        MatchTargetsCandidate(
            state=state,
            is_exposed=(
                async_should_expose(hass, constraints.assistant, state.entity_id)
                if constraints.assistant
                else True
            ),
        )
        for state in states
    ]

    if constraints.domains and (not filtered_by_domain):
        # Filter by domain (if we didn't already do it)
        candidates = [c for c in candidates if c.state.domain in constraints.domains]
        if not candidates:
            return MatchTargetsResult(False, MatchFailedReason.DOMAIN)

    if constraints.states:
        # Filter by state
        candidates = [c for c in candidates if c.state.state in constraints.states]
        if not candidates:
            return MatchTargetsResult(False, MatchFailedReason.STATE)

    # Try to exit early so we can avoid registry lookups
    if not (
        constraints.name
        or constraints.features
        or constraints.device_classes
        or constraints.area_name
        or constraints.floor_name
    ):
        if constraints.assistant:
            # Check exposure
            candidates = [c for c in candidates if c.is_exposed]
            if not candidates:
                return MatchTargetsResult(False, MatchFailedReason.ASSISTANT)

        return MatchTargetsResult(True, states=[c.state for c in candidates])

    # We need entity registry entries now
    ent_reg = er.async_get(hass)
    for candidate in candidates:
        candidate.entity = ent_reg.async_get(candidate.state.entity_id)

    if constraints.name:
        # Filter by entity name or alias
        candidates = list(_filter_by_name(constraints.name, candidates))
        if not candidates:
            return MatchTargetsResult(False, MatchFailedReason.NAME)

    if constraints.features:
        # Filter by supported features
        candidates = list(_filter_by_features(constraints.features, candidates))
        if not candidates:
            return MatchTargetsResult(False, MatchFailedReason.FEATURE)

    if constraints.device_classes:
        # Filter by device class
        candidates = list(
            _filter_by_device_classes(constraints.device_classes, candidates)
        )
        if not candidates:
            return MatchTargetsResult(False, MatchFailedReason.DEVICE_CLASS)

    # Check area constraints
    # Check exposure
    # Check for duplicates
    candidates, targeted_areas, match_result = (
        _async_match_areas_assistant_and_duplicates(
            hass, constraints, preferences, candidates
        )
    )

    if match_result is not None:
        return match_result

    return MatchTargetsResult(
        True,
        None,
        states=[c.state for c in candidates],
        areas=targeted_areas or [],
    )
