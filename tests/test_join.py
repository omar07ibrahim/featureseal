"""Point-in-time selection edge cases."""

from __future__ import annotations

from featureseal.join import expected_selections
from featureseal.model import parse_snapshot


def _document(
    *,
    at: int,
    max_age: int,
    selected: str | None = None,
) -> dict[str, object]:
    return {
        "format": "featureseal.snapshot.v1",
        "snapshot_id": "join-edge",
        "features": [
            {"name": "score", "value_type": "number", "max_age_seconds": max_age}
        ],
        "events": [
            {
                "event_id": "older",
                "entity": "acct-a",
                "feature": "score",
                "event_time": 10,
                "available_time": 10,
                "value": 0.1,
                "source": "risk",
            },
            {
                "event_id": "newer",
                "entity": "acct-a",
                "feature": "score",
                "event_time": 20,
                "available_time": 40,
                "value": 0.9,
                "source": "risk",
            },
        ],
        "observations": [
            {
                "observation_id": "obs",
                "entity": "acct-a",
                "at": at,
                "selections": {"score": selected},
            }
        ],
    }


def test_unavailable_latest_falls_back_to_older() -> None:
    snapshot = parse_snapshot(_document(at=30, max_age=100))
    assert expected_selections(snapshot)[("obs", "score")] == "older"


def test_latest_becomes_eligible_at_availability_time() -> None:
    snapshot = parse_snapshot(_document(at=40, max_age=100))
    assert expected_selections(snapshot)[("obs", "score")] == "newer"


def test_expired_history_yields_no_selection() -> None:
    snapshot = parse_snapshot(_document(at=200, max_age=100))
    assert expected_selections(snapshot)[("obs", "score")] is None


def test_zero_freshness_accepts_exact_event_time() -> None:
    snapshot = parse_snapshot(_document(at=20, max_age=0))
    assert expected_selections(snapshot)[("obs", "score")] is None
