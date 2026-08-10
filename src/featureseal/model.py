"""Strict bounded snapshot contract for point-in-time feature joins."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TypeAlias, cast

from featureseal.errors import ContractError

SNAPSHOT_FORMAT = "featureseal.snapshot.v1"
MAX_FEATURES = 16
MAX_EVENTS = 512
MAX_OBSERVATIONS = 128
MAX_TIME = 2**32 - 1
MAX_ABS_NUMBER = 10**15
_NAME = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_FEATURE_KEYS = {"name", "value_type", "max_age_seconds"}
_EVENT_KEYS = {
    "event_id",
    "entity",
    "feature",
    "event_time",
    "available_time",
    "value",
    "source",
}
_OBSERVATION_KEYS = {"observation_id", "entity", "at", "selections"}
_SNAPSHOT_KEYS = {"format", "snapshot_id", "features", "events", "observations"}
_VALUE_TYPES = {"boolean", "integer", "number", "string"}

Scalar: TypeAlias = bool | int | float | str


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    name: str
    value_type: str
    max_age_seconds: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value_type": self.value_type,
            "max_age_seconds": self.max_age_seconds,
        }


@dataclass(frozen=True, slots=True)
class FeatureEvent:
    event_id: str
    entity: str
    feature: str
    event_time: int
    available_time: int
    value: Scalar
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "entity": self.entity,
            "feature": self.feature,
            "event_time": self.event_time,
            "available_time": self.available_time,
            "value": self.value,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class Observation:
    observation_id: str
    entity: str
    at: int
    selections: dict[str, str | None]

    def to_dict(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "entity": self.entity,
            "at": self.at,
            "selections": dict(sorted(self.selections.items())),
        }


@dataclass(frozen=True, slots=True)
class Snapshot:
    snapshot_id: str
    features: tuple[FeatureSpec, ...]
    events: tuple[FeatureEvent, ...]
    observations: tuple[Observation, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "format": SNAPSHOT_FORMAT,
            "snapshot_id": self.snapshot_id,
            "features": [feature.to_dict() for feature in self.features],
            "events": [event.to_dict() for event in self.events],
            "observations": [observation.to_dict() for observation in self.observations],
        }


def _as_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContractError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _exact_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ContractError(f"{label} fields differ: {sorted(actual ^ expected)}")


def _name(value: object, label: str) -> str:
    if not isinstance(value, str) or _NAME.fullmatch(value) is None:
        raise ContractError(f"{label} must match {_NAME.pattern}")
    return value


def _bounded_int(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= MAX_TIME:
        raise ContractError(f"{label} must be an integer in {minimum}..{MAX_TIME}")
    return value


def _scalar(value: object, value_type: str, label: str) -> Scalar:
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise ContractError(f"{label} must be boolean")
        return value
    if value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int) or abs(value) > MAX_ABS_NUMBER:
            raise ContractError(f"{label} must be a bounded integer")
        return value
    if value_type == "number":
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or abs(value) > MAX_ABS_NUMBER
            or not math.isfinite(float(value))
        ):
            raise ContractError(f"{label} must be a bounded finite number")
        return value
    if not isinstance(value, str) or len(value) > 256:
        raise ContractError(f"{label} must be a string of at most 256 characters")
    return value


def parse_snapshot(document: object) -> Snapshot:
    """Validate and normalize a complete snapshot."""

    root = _as_object(document, "snapshot")
    _exact_keys(root, _SNAPSHOT_KEYS, "snapshot")
    if root["format"] != SNAPSHOT_FORMAT:
        raise ContractError(f"snapshot format must be {SNAPSHOT_FORMAT}")
    snapshot_id = _name(root["snapshot_id"], "snapshot_id")

    raw_features = root["features"]
    if not isinstance(raw_features, list) or not 1 <= len(raw_features) <= MAX_FEATURES:
        raise ContractError(f"features must contain 1..{MAX_FEATURES} entries")
    features: list[FeatureSpec] = []
    for index, raw in enumerate(raw_features):
        value = _as_object(raw, f"features[{index}]")
        _exact_keys(value, _FEATURE_KEYS, f"features[{index}]")
        value_type = value["value_type"]
        if value_type not in _VALUE_TYPES:
            raise ContractError(f"features[{index}].value_type is invalid")
        features.append(
            FeatureSpec(
                name=_name(value["name"], f"features[{index}].name"),
                value_type=value_type,
                max_age_seconds=_bounded_int(
                    value["max_age_seconds"],
                    f"features[{index}].max_age_seconds",
                ),
            )
        )
    feature_by_name = {feature.name: feature for feature in features}
    if len(feature_by_name) != len(features):
        raise ContractError("feature names must be unique")
    feature_names = set(feature_by_name)

    raw_events = root["events"]
    if not isinstance(raw_events, list) or not 1 <= len(raw_events) <= MAX_EVENTS:
        raise ContractError(f"events must contain 1..{MAX_EVENTS} entries")
    events: list[FeatureEvent] = []
    for index, raw in enumerate(raw_events):
        value = _as_object(raw, f"events[{index}]")
        _exact_keys(value, _EVENT_KEYS, f"events[{index}]")
        feature_name = _name(value["feature"], f"events[{index}].feature")
        spec = feature_by_name.get(feature_name)
        if spec is None:
            raise ContractError(f"events[{index}] references unknown feature {feature_name}")
        event_time = _bounded_int(value["event_time"], f"events[{index}].event_time")
        available_time = _bounded_int(
            value["available_time"],
            f"events[{index}].available_time",
        )
        if available_time < event_time:
            raise ContractError(f"events[{index}].available_time precedes event_time")
        events.append(
            FeatureEvent(
                event_id=_name(value["event_id"], f"events[{index}].event_id"),
                entity=_name(value["entity"], f"events[{index}].entity"),
                feature=feature_name,
                event_time=event_time,
                available_time=available_time,
                value=_scalar(value["value"], spec.value_type, f"events[{index}].value"),
                source=_name(value["source"], f"events[{index}].source"),
            )
        )
    event_by_id = {event.event_id: event for event in events}
    if len(event_by_id) != len(events):
        raise ContractError("event_id values must be unique")
    coordinates = {(event.entity, event.feature, event.event_time) for event in events}
    if len(coordinates) != len(events):
        raise ContractError("entity/feature/event_time coordinates must be unique")

    raw_observations = root["observations"]
    if not isinstance(raw_observations, list) or not 1 <= len(raw_observations) <= MAX_OBSERVATIONS:
        raise ContractError(f"observations must contain 1..{MAX_OBSERVATIONS} entries")
    observations: list[Observation] = []
    for index, raw in enumerate(raw_observations):
        value = _as_object(raw, f"observations[{index}]")
        _exact_keys(value, _OBSERVATION_KEYS, f"observations[{index}]")
        raw_selections = _as_object(
            value["selections"],
            f"observations[{index}].selections",
        )
        _exact_keys(raw_selections, feature_names, f"observations[{index}].selections")
        selections: dict[str, str | None] = {}
        for feature_name in sorted(feature_names):
            selected = raw_selections[feature_name]
            if selected is None:
                selections[feature_name] = None
            else:
                event_id = _name(
                    selected,
                    f"observations[{index}].selections.{feature_name}",
                )
                if event_id not in event_by_id:
                    raise ContractError(f"observations[{index}] selects unknown event {event_id}")
                selections[feature_name] = event_id
        observations.append(
            Observation(
                observation_id=_name(
                    value["observation_id"],
                    f"observations[{index}].observation_id",
                ),
                entity=_name(value["entity"], f"observations[{index}].entity"),
                at=_bounded_int(value["at"], f"observations[{index}].at"),
                selections=selections,
            )
        )
    observation_ids = [item.observation_id for item in observations]
    if len(observation_ids) != len(set(observation_ids)):
        raise ContractError("observation_id values must be unique")

    return Snapshot(
        snapshot_id=snapshot_id,
        features=tuple(sorted(features, key=lambda item: item.name)),
        events=tuple(
            sorted(
                events,
                key=lambda item: (
                    item.available_time,
                    item.event_time,
                    item.event_id,
                ),
            )
        ),
        observations=tuple(sorted(observations, key=lambda item: (item.at, item.observation_id))),
    )
