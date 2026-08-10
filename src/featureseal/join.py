"""Analyzer-side point-in-time selection using indexed reverse scans."""

from __future__ import annotations

from bisect import bisect_right

from featureseal.model import FeatureEvent, Observation, Snapshot


def expected_selections(snapshot: Snapshot) -> dict[tuple[str, str], str | None]:
    """Return the newest event that was both valid and available at each observation."""

    grouped: dict[tuple[str, str], list[FeatureEvent]] = {}
    for event in snapshot.events:
        grouped.setdefault((event.entity, event.feature), []).append(event)
    for events in grouped.values():
        events.sort(key=lambda item: (item.event_time, item.event_id))

    result: dict[tuple[str, str], str | None] = {}
    for observation in snapshot.observations:
        for spec in snapshot.features:
            events = grouped.get((observation.entity, spec.name), [])
            times = [event.event_time for event in events]
            position = bisect_right(times, observation.at)
            selected: str | None = None
            for index in range(position - 1, -1, -1):
                event = events[index]
                if observation.at - event.event_time > spec.max_age_seconds:
                    break
                if event.available_time <= observation.at:
                    selected = event.event_id
                    break
            result[(observation.observation_id, spec.name)] = selected
    return result


def classify_mismatch(
    *,
    observation: Observation,
    feature: str,
    max_age_seconds: int,
    selected: str | None,
    expected: str | None,
    event_by_id: dict[str, FeatureEvent],
) -> str | None:
    """Classify one non-matching join cell with one deterministic primary reason."""

    if selected == expected:
        return None
    if selected is None:
        return "MISSING_SELECTION"
    event = event_by_id[selected]
    if event.entity != observation.entity or event.feature != feature:
        return "IDENTITY_MISMATCH"
    if event.event_time > observation.at:
        return "FUTURE_EVENT"
    if event.available_time > observation.at:
        return "UNAVAILABLE_EVENT"
    if observation.at - event.event_time > max_age_seconds:
        return "EXPIRED_EVENT"
    return "STALE_SELECTION"
