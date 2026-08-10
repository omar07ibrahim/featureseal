"""Independent verifier mutation tests."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import cast

import pytest

from featureseal.engine import analyze_document
from featureseal.errors import VerificationError
from featureseal.verify import verify_receipt

Mutation = Callable[[dict[str, object]], None]


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value)


def _sequence(value: object) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], value)


def _mutate_summary(receipt: dict[str, object]) -> None:
    _mapping(receipt["summary"])["cells"] = 999


def _mutate_cells(receipt: dict[str, object]) -> None:
    _sequence(receipt["cells"])[0]["status"] = "FUTURE_EVENT"


def _mutate_finding(receipt: dict[str, object]) -> None:
    _sequence(receipt["findings"])[0]["expected_event"] = None


def _mutate_ledger(receipt: dict[str, object]) -> None:
    _sequence(receipt["ledger"])[0]["payload_sha256"] = "0" * 64


def _mutate_root(receipt: dict[str, object]) -> None:
    receipt["ledger_root_sha256"] = "0" * 64


def _mutate_snapshot_hash(receipt: dict[str, object]) -> None:
    receipt["snapshot_sha256"] = "0" * 64


def _mutate_receipt_hash(receipt: dict[str, object]) -> None:
    receipt["receipt_sha256"] = "f" * 64


def _mutate_snapshot(receipt: dict[str, object]) -> None:
    snapshot = _mapping(receipt["snapshot"])
    _sequence(snapshot["events"])[0]["value"] = 121


@pytest.mark.parametrize(
    "mutation",
    [
        _mutate_summary,
        _mutate_cells,
        _mutate_finding,
        _mutate_ledger,
        _mutate_root,
        _mutate_snapshot_hash,
        _mutate_receipt_hash,
        _mutate_snapshot,
    ],
)
def test_mutated_receipt_is_rejected(
    incident: dict[str, object],
    mutation: Mutation,
) -> None:
    receipt = copy.deepcopy(analyze_document(incident))
    mutation(receipt)
    with pytest.raises(VerificationError, match="does not replay"):
        verify_receipt(receipt)


def test_missing_field_is_rejected(incident: dict[str, object]) -> None:
    receipt = analyze_document(incident)
    del receipt["cells"]
    with pytest.raises(VerificationError, match="fields differ"):
        verify_receipt(receipt)


def test_extra_field_is_rejected(incident: dict[str, object]) -> None:
    receipt = analyze_document(incident)
    receipt["trusted"] = True
    with pytest.raises(VerificationError, match="fields differ"):
        verify_receipt(receipt)


def test_wrong_format_is_rejected(incident: dict[str, object]) -> None:
    receipt = analyze_document(incident)
    receipt["format"] = "featureseal.receipt.v2"
    with pytest.raises(VerificationError, match="receipt format"):
        verify_receipt(receipt)


def test_missing_snapshot_is_rejected(incident: dict[str, object]) -> None:
    receipt = analyze_document(incident)
    del receipt["snapshot"]
    with pytest.raises(VerificationError, match="snapshot is invalid"):
        verify_receipt(receipt)


@pytest.mark.parametrize("document", [None, [], "receipt", 4])
def test_non_object_receipt_is_rejected(document: object) -> None:
    with pytest.raises(VerificationError, match="must be an object"):
        verify_receipt(document)
