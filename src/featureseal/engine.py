"""Compose complete deterministic FeatureSeal receipts."""

from __future__ import annotations

from featureseal.analyze import analyze
from featureseal.canonical import sha256_value
from featureseal.ledger import build_ledger
from featureseal.model import parse_snapshot

RECEIPT_FORMAT = "featureseal.receipt.v1"


def analyze_document(document: object) -> dict[str, object]:
    """Validate one snapshot and return its complete receipt."""

    snapshot = parse_snapshot(document)
    cells, findings, summary = analyze(snapshot)
    ledger, root = build_ledger(snapshot, findings)
    core: dict[str, object] = {
        "format": RECEIPT_FORMAT,
        "snapshot": snapshot.to_dict(),
        "snapshot_sha256": sha256_value(snapshot.to_dict()),
        "cells": cells,
        "findings": findings,
        "summary": summary,
        "ledger": ledger,
        "ledger_root_sha256": root,
    }
    return {**core, "receipt_sha256": sha256_value(core)}
