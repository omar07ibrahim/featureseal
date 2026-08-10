"""Detect point-in-time leakage, freshness, and identity mismatches."""

from __future__ import annotations

from collections import Counter

from featureseal.canonical import sha256_value
from featureseal.join import classify_mismatch, expected_selections
from featureseal.model import FeatureEvent, Observation, Snapshot

RULES = (
    "FUTURE_EVENT",
    "UNAVAILABLE_EVENT",
    "IDENTITY_MISMATCH",
    "EXPIRED_EVENT",
    "STALE_SELECTION",
    "MISSING_SELECTION",
)


def _explanation(
    rule: str,
    observation: Observation,
    feature: str,
    selected: str | None,
    expected: str | None,
    event_by_id: dict[str, FeatureEvent],
) -> str:
    if rule == "MISSING_SELECTION":
        return f"{observation.observation_id} omits eligible event {expected} for {feature}"
    assert selected is not None
    event = event_by_id[selected]
    if rule == "IDENTITY_MISMATCH":
        return (
            f"{selected} belongs to {event.entity}/{event.feature}, not "
            f"{observation.entity}/{feature}"
        )
    if rule == "FUTURE_EVENT":
        return f"{selected} has event_time {event.event_time} after {observation.at}"
    if rule == "UNAVAILABLE_EVENT":
        return f"{selected} became available at {event.available_time} after {observation.at}"
    if rule == "EXPIRED_EVENT":
        return f"{selected} is outside the {feature} freshness window at {observation.at}"
    return f"{selected} is not the newest eligible event; expected {expected}"


def _finding(
    *,
    rule: str,
    observation: Observation,
    feature: str,
    selected: str | None,
    expected: str | None,
    event_by_id: dict[str, FeatureEvent],
) -> dict[str, object]:
    witness_events = list(
        dict.fromkeys(event for event in (selected, expected) if event is not None)
    )
    body: dict[str, object] = {
        "rule": rule,
        "observation_id": observation.observation_id,
        "entity": observation.entity,
        "feature": feature,
        "at": observation.at,
        "selected_event": selected,
        "expected_event": expected,
        "witness_events": witness_events,
        "explanation": _explanation(
            rule,
            observation,
            feature,
            selected,
            expected,
            event_by_id,
        ),
    }
    return {"finding_id": "FS-" + sha256_value(body)[:12].upper(), **body}


def analyze(
    snapshot: Snapshot,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """Build canonical join cells, primary findings, and an exact summary."""

    expected = expected_selections(snapshot)
    event_by_id = {event.event_id: event for event in snapshot.events}
    cells: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []

    for observation in snapshot.observations:
        for spec in snapshot.features:
            selected = observation.selections[spec.name]
            expected_event = expected[(observation.observation_id, spec.name)]
            rule = classify_mismatch(
                observation=observation,
                feature=spec.name,
                max_age_seconds=spec.max_age_seconds,
                selected=selected,
                expected=expected_event,
                event_by_id=event_by_id,
            )
            cells.append(
                {
                    "observation_id": observation.observation_id,
                    "entity": observation.entity,
                    "at": observation.at,
                    "feature": spec.name,
                    "selected_event": selected,
                    "expected_event": expected_event,
                    "status": rule or "MATCH",
                }
            )
            if rule is not None:
                findings.append(
                    _finding(
                        rule=rule,
                        observation=observation,
                        feature=spec.name,
                        selected=selected,
                        expected=expected_event,
                        event_by_id=event_by_id,
                    )
                )

    counts = Counter(str(finding["rule"]) for finding in findings)
    summary: dict[str, object] = {
        "features": len(snapshot.features),
        "events": len(snapshot.events),
        "observations": len(snapshot.observations),
        "entities": len(
            {event.entity for event in snapshot.events}
            | {observation.entity for observation in snapshot.observations}
        ),
        "cells": len(cells),
        "matched_cells": len(cells) - len(findings),
        "finding_cells": len(findings),
        "rule_counts": {rule: counts[rule] for rule in RULES},
    }
    return cells, findings, summary
