"""Bounded JSON parsing and canonical SHA-256 helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from featureseal.errors import ContractError

MAX_SNAPSHOT_BYTES = 1024 * 1024
MAX_RECEIPT_BYTES = 4 * 1024 * 1024


def _object_from_pairs(pairs: Iterable[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ContractError(f"non-finite JSON number: {value}")


def parse_json_bytes(data: bytes, *, max_bytes: int) -> object:
    """Parse bounded UTF-8 JSON while rejecting duplicate keys and non-finite values."""

    if len(data) > max_bytes:
        raise ContractError(f"JSON exceeds {max_bytes} bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("JSON must be UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_from_pairs,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ContractError("invalid JSON document") from exc
    return cast(object, value)


def load_json(path: Path, *, max_bytes: int) -> object:
    """Load one bounded local JSON document."""

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read {path}") from exc
    return parse_json_bytes(data, max_bytes=max_bytes)


def canonical_bytes(value: object) -> bytes:
    """Encode a JSON-compatible value with one deterministic representation."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ContractError("value is not canonical JSON") from exc
    return encoded.encode("utf-8")


def sha256_value(value: object) -> str:
    """Return a canonical JSON SHA-256 digest."""

    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def pretty_json(value: object) -> str:
    """Return stable indented JSON with a final newline."""

    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ContractError("value is not JSON serializable") from exc
