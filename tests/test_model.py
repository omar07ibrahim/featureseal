"""Strict contract and bounded JSON tests."""

from __future__ import annotations

import copy
from typing import cast

import pytest

from featureseal.canonical import parse_json_bytes
from featureseal.errors import ContractError
from featureseal.model import MAX_ABS_NUMBER, parse_snapshot


def _broken(incident: dict[str, object], case: str) -> object:
    document = copy.deepcopy(incident)
    features = cast(list[dict[str, object]], document["features"])
    events = cast(list[dict[str, object]], document["events"])
    observations = cast(list[dict[str, object]], document["observations"])
    if case == "root-not-object":
        return []
    if case == "extra-root":
        document["extra"] = True
    elif case == "wrong-format":
        document["format"] = "featureseal.snapshot.v2"
    elif case == "no-features":
        document["features"] = []
    elif case == "too-many-features":
        document["features"] = [copy.deepcopy(features[0]) for _ in range(17)]
    elif case == "duplicate-feature":
        features.append(copy.deepcopy(features[0]))
    elif case == "bad-feature-name":
        features[0]["name"] = "Bad Name"
    elif case == "bad-value-type":
        features[0]["value_type"] = "vector"
    elif case == "negative-age":
        features[0]["max_age_seconds"] = -1
    elif case == "boolean-age":
        features[0]["max_age_seconds"] = True
    elif case == "no-events":
        document["events"] = []
    elif case == "unknown-feature":
        events[0]["feature"] = "unknown"
    elif case == "availability-before-event":
        events[0]["available_time"] = 99
    elif case == "duplicate-event-id":
        events[1]["event_id"] = events[0]["event_id"]
    elif case == "duplicate-coordinate":
        events[1].update(
            {
                "entity": events[0]["entity"],
                "feature": events[0]["feature"],
                "event_time": events[0]["event_time"],
                "available_time": events[0]["available_time"],
                "value": 5,
            }
        )
    elif case == "bad-event-name":
        events[0]["event_id"] = "../event"
    elif case == "wrong-value":
        events[0]["value"] = "not-an-integer"
    elif case == "huge-value":
        events[0]["value"] = MAX_ABS_NUMBER + 1
    elif case == "no-observations":
        document["observations"] = []
    elif case == "duplicate-observation":
        observations.append(copy.deepcopy(observations[0]))
    elif case == "missing-selection":
        cast(dict[str, object], observations[0]["selections"]).pop("risk_score")
    elif case == "extra-selection":
        cast(dict[str, object], observations[0]["selections"])["other"] = None
    elif case == "unknown-selected-event":
        cast(dict[str, object], observations[0]["selections"])["risk_score"] = "missing"
    elif case == "boolean-observation-time":
        observations[0]["at"] = True
    elif case == "bad-entity-name":
        observations[0]["entity"] = "ACCT"
    else:
        raise AssertionError(case)
    return document


@pytest.mark.parametrize(
    "case",
    [
        "root-not-object",
        "extra-root",
        "wrong-format",
        "no-features",
        "too-many-features",
        "duplicate-feature",
        "bad-feature-name",
        "bad-value-type",
        "negative-age",
        "boolean-age",
        "no-events",
        "unknown-feature",
        "availability-before-event",
        "duplicate-event-id",
        "duplicate-coordinate",
        "bad-event-name",
        "wrong-value",
        "huge-value",
        "no-observations",
        "duplicate-observation",
        "missing-selection",
        "extra-selection",
        "unknown-selected-event",
        "boolean-observation-time",
        "bad-entity-name",
    ],
)
def test_invalid_snapshot_is_rejected(
    incident: dict[str, object],
    case: str,
) -> None:
    with pytest.raises(ContractError):
        parse_snapshot(_broken(incident, case))


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        ("boolean", True),
        ("integer", 7),
        ("number", 7),
        ("number", 0.25),
        ("string", "segment-a"),
    ],
)
def test_supported_feature_values_are_accepted(value_type: str, value: object) -> None:
    document = {
        "format": "featureseal.snapshot.v1",
        "snapshot_id": "types",
        "features": [
            {"name": "value", "value_type": value_type, "max_age_seconds": 10}
        ],
        "events": [
            {
                "event_id": "value-1",
                "entity": "acct",
                "feature": "value",
                "event_time": 1,
                "available_time": 1,
                "value": value,
                "source": "source",
            }
        ],
        "observations": [
            {
                "observation_id": "obs",
                "entity": "acct",
                "at": 1,
                "selections": {"value": "value-1"},
            }
        ],
    }
    assert parse_snapshot(document).events[0].value == value


@pytest.mark.parametrize(
    "data",
    [
        b'{"x": 1, "x": 2}',
        b'{"x": NaN}',
        b'{"x": Infinity}',
        b"{",
        b"\xff",
    ],
)
def test_invalid_json_bytes_are_rejected(data: bytes) -> None:
    with pytest.raises(ContractError):
        parse_json_bytes(data, max_bytes=100)


def test_json_byte_limit_is_enforced() -> None:
    with pytest.raises(ContractError, match="exceeds"):
        parse_json_bytes(b'{"value": 1}', max_bytes=3)
