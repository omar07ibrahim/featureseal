"""Analyzer semantics, normalization, and receipt determinism."""

from __future__ import annotations

import copy
from typing import cast

from featureseal.analyze import RULES
from featureseal.engine import analyze_document
from featureseal.verify import verify_receipt


def _summary(receipt: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], receipt["summary"])


def _findings(receipt: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], receipt["findings"])


def _cells(receipt: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], receipt["cells"])


def _clean_snapshot() -> dict[str, object]:
    return {
        "format": "featureseal.snapshot.v1",
        "snapshot_id": "clean",
        "features": [
            {"name": "score", "value_type": "number", "max_age_seconds": 100}
        ],
        "events": [
            {
                "event_id": "score-1",
                "entity": "acct-a",
                "feature": "score",
                "event_time": 10,
                "available_time": 10,
                "value": 0.4,
                "source": "risk",
            }
        ],
        "observations": [
            {
                "observation_id": "obs-1",
                "entity": "acct-a",
                "at": 20,
                "selections": {"score": "score-1"},
            }
        ],
    }


def test_incident_summary_is_exact(incident: dict[str, object]) -> None:
    assert _summary(analyze_document(incident)) == {
        "features": 4,
        "events": 18,
        "observations": 7,
        "entities": 3,
        "cells": 28,
        "matched_cells": 22,
        "finding_cells": 6,
        "rule_counts": {
            "FUTURE_EVENT": 1,
            "UNAVAILABLE_EVENT": 1,
            "IDENTITY_MISMATCH": 1,
            "EXPIRED_EVENT": 1,
            "STALE_SELECTION": 1,
            "MISSING_SELECTION": 1,
        },
    }


def test_incident_finding_order_is_exact(incident: dict[str, object]) -> None:
    findings = _findings(analyze_document(incident))
    assert [
        (item["observation_id"], item["feature"], item["rule"])
        for item in findings
    ] == [
        ("obs-a-620", "risk_score", "STALE_SELECTION"),
        ("obs-a-700", "device_trust", "UNAVAILABLE_EVENT"),
        ("obs-a-750", "risk_score", "FUTURE_EVENT"),
        ("obs-b-750", "country_tier", "IDENTITY_MISMATCH"),
        ("obs-b-750", "device_trust", "MISSING_SELECTION"),
        ("obs-a-1000", "device_trust", "EXPIRED_EVENT"),
    ]


def test_all_rules_have_one_public_witness(incident: dict[str, object]) -> None:
    findings = _findings(analyze_document(incident))
    assert {item["rule"] for item in findings} == set(RULES)
    assert all(len(cast(list[str], item["witness_events"])) in {1, 2} for item in findings)


def test_selected_and_expected_witnesses_are_explicit(incident: dict[str, object]) -> None:
    findings = {
        str(item["rule"]): item for item in _findings(analyze_document(incident))
    }
    assert findings["FUTURE_EVENT"]["selected_event"] == "a-risk-3"
    assert findings["FUTURE_EVENT"]["expected_event"] == "a-risk-2"
    assert findings["UNAVAILABLE_EVENT"]["selected_event"] == "a-device-2"
    assert findings["UNAVAILABLE_EVENT"]["expected_event"] == "a-device-1"
    assert findings["MISSING_SELECTION"]["selected_event"] is None
    assert findings["MISSING_SELECTION"]["expected_event"] == "b-device-1"
    assert findings["EXPIRED_EVENT"]["expected_event"] is None


def test_cell_status_counts_match_summary(incident: dict[str, object]) -> None:
    cells = _cells(analyze_document(incident))
    assert len([item for item in cells if item["status"] == "MATCH"]) == 22
    assert len([item for item in cells if item["status"] != "MATCH"]) == 6


def test_finding_ids_are_unique_and_content_bound(incident: dict[str, object]) -> None:
    identifiers = [
        str(item["finding_id"]) for item in _findings(analyze_document(incident))
    ]
    assert len(identifiers) == len(set(identifiers))
    assert all(identifier.startswith("FS-") and len(identifier) == 15 for identifier in identifiers)


def test_ledger_covers_inputs_then_findings(incident: dict[str, object]) -> None:
    receipt = analyze_document(incident)
    ledger = cast(list[dict[str, object]], receipt["ledger"])
    assert len(ledger) == 35
    assert [item["kind"] for item in ledger[:4]] == ["feature"] * 4
    assert [item["kind"] for item in ledger[4:22]] == ["event"] * 18
    assert [item["kind"] for item in ledger[22:29]] == ["observation"] * 7
    assert [item["kind"] for item in ledger[29:]] == ["finding"] * 6
    assert ledger[0]["previous_sha256"] == "0" * 64
    assert ledger[-1]["entry_sha256"] == receipt["ledger_root_sha256"]


def test_analysis_is_deterministic(incident: dict[str, object]) -> None:
    assert analyze_document(incident) == analyze_document(copy.deepcopy(incident))


def test_input_list_order_is_normalized(incident: dict[str, object]) -> None:
    shuffled = copy.deepcopy(incident)
    for key in ("features", "events", "observations"):
        cast(list[object], shuffled[key]).reverse()
    assert analyze_document(shuffled) == analyze_document(incident)


def test_independent_sqlite_verifier_matches(incident: dict[str, object]) -> None:
    receipt = analyze_document(incident)
    assert verify_receipt(receipt) == receipt["summary"]


def test_clean_snapshot_has_no_findings() -> None:
    receipt = analyze_document(_clean_snapshot())
    assert _findings(receipt) == []
    assert _summary(receipt)["matched_cells"] == 1
    assert verify_receipt(receipt) == receipt["summary"]
