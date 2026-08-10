"""Hash-chain normalized inputs and every join finding."""

from __future__ import annotations

from featureseal.canonical import sha256_value
from featureseal.model import Snapshot


def build_ledger(
    snapshot: Snapshot,
    findings: list[dict[str, object]],
) -> tuple[list[dict[str, object]], str]:
    payloads: list[tuple[str, object]] = [
        ("feature", feature.to_dict()) for feature in snapshot.features
    ]
    payloads.extend(("event", event.to_dict()) for event in snapshot.events)
    payloads.extend(("observation", observation.to_dict()) for observation in snapshot.observations)
    payloads.extend(("finding", finding) for finding in findings)

    previous = "0" * 64
    entries: list[dict[str, object]] = []
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
