"""Independent receipt replay backed by an in-memory SQLite query plan.

This module deliberately does not import the analyzer, indexed join selector,
ledger, or engine. It reconstructs their public contract through parameterized
relational queries and an independent hash-chain implementation.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import cast

from featureseal.canonical import sha256_value
from featureseal.errors import VerificationError
from featureseal.model import FeatureEvent, Observation, Snapshot, parse_snapshot

_RECEIPT_FORMAT = "featureseal.receipt.v1"
_RULES = (
    "FUTURE_EVENT",
    "UNAVAILABLE_EVENT",
    "IDENTITY_MISMATCH",
    "EXPIRED_EVENT",
    "STALE_SELECTION",
    "MISSING_SELECTION",
)


def _expected(snapshot: Snapshot) -> dict[tuple[str, str], str | None]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute(
            """
            CREATE TABLE feature_events (
                event_id TEXT PRIMARY KEY,
                entity TEXT NOT NULL,
                feature TEXT NOT NULL,
                event_time INTEGER NOT NULL,
                available_time INTEGER NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO feature_events
                (event_id, entity, feature, event_time, available_time)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    event.event_id,
                    event.entity,
                    event.feature,
                    event.event_time,
                    event.available_time,
                )
                for event in snapshot.events
            ],
        )
        result: dict[tuple[str, str], str | None] = {}
        for observation in snapshot.observations:
            for spec in snapshot.features:
                row = connection.execute(
                    """
                    SELECT event_id
                    FROM feature_events
                    WHERE entity = ?
                      AND feature = ?
                      AND event_time <= ?
                      AND available_time <= ?
                      AND (? - event_time) <= ?
                    ORDER BY event_time DESC, event_id DESC
                    LIMIT 1
                    """,
                    (
                        observation.entity,
                        spec.name,
                        observation.at,
                        observation.at,
                        observation.at,
                        spec.max_age_seconds,
                    ),
                ).fetchone()
                result[(observation.observation_id, spec.name)] = (
                    cast(str, row[0]) if row is not None else None
                )
        return result
    finally:
        connection.close()


def _rule(
    observation: Observation,
    feature: str,
    max_age_seconds: int,
    selected: str | None,
    expected: str | None,
    event_by_id: dict[str, FeatureEvent],
) -> str | None:
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
    witnesses = list(dict.fromkeys(event for event in (selected, expected) if event is not None))
    body: dict[str, object] = {
        "rule": rule,
        "observation_id": observation.observation_id,
        "entity": observation.entity,
        "feature": feature,
        "at": observation.at,
        "selected_event": selected,
        "expected_event": expected,
        "witness_events": witnesses,
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


def _replay(
    snapshot: Snapshot,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    expected = _expected(snapshot)
    event_by_id = {event.event_id: event for event in snapshot.events}
    cells: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    for observation in snapshot.observations:
        for spec in snapshot.features:
            selected = observation.selections[spec.name]
            expected_event = expected[(observation.observation_id, spec.name)]
            rule = _rule(
                observation,
                spec.name,
                spec.max_age_seconds,
                selected,
                expected_event,
                event_by_id,
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
        "rule_counts": {rule: counts[rule] for rule in _RULES},
    }
    return cells, findings, summary


def _ledger(
    snapshot: Snapshot,
    findings: list[dict[str, object]],
) -> tuple[list[dict[str, object]], str]:
    payloads: list[tuple[str, object]] = [
        ("feature", feature.to_dict()) for feature in snapshot.features
    ]
    payloads.extend(("event", event.to_dict()) for event in snapshot.events)
    payloads.extend(("observation", observation.to_dict()) for observation in snapshot.observations)
    payloads.extend(("finding", finding) for finding in findings)
    entries: list[dict[str, object]] = []
    previous = "0" * 64
    for index, (kind, payload) in enumerate(payloads):
        material: dict[str, object] = {
            "index": index,
            "kind": kind,
            "previous_sha256": previous,
            "payload_sha256": sha256_value(payload),
        }
        digest = sha256_value(material)
        entries.append({**material, "entry_sha256": digest})
        previous = digest
    return entries, previous


def verify_receipt(document: object) -> dict[str, object]:
    """Replay every receipt field and return the independently derived summary."""

    if not isinstance(document, dict):
        raise VerificationError("receipt must be an object")
    receipt = cast(dict[str, object], document)
    if receipt.get("format") != _RECEIPT_FORMAT:
        raise VerificationError(f"receipt format must be {_RECEIPT_FORMAT}")
    try:
        snapshot = parse_snapshot(receipt["snapshot"])
    except (KeyError, ValueError) as exc:
        raise VerificationError("receipt snapshot is invalid") from exc

    cells, findings, summary = _replay(snapshot)
    ledger, root = _ledger(snapshot, findings)
    core: dict[str, object] = {
        "format": _RECEIPT_FORMAT,
        "snapshot": snapshot.to_dict(),
        "snapshot_sha256": sha256_value(snapshot.to_dict()),
        "cells": cells,
        "findings": findings,
        "summary": summary,
        "ledger": ledger,
        "ledger_root_sha256": root,
    }
    expected = {**core, "receipt_sha256": sha256_value(core)}
    if set(receipt) != set(expected):
        raise VerificationError("receipt fields differ")
    for key, value in expected.items():
        if receipt[key] != value:
            raise VerificationError(f"receipt {key} does not replay")
    return summary
