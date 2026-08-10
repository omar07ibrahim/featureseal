"""FeatureSeal command-line interface."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from featureseal.canonical import (
    MAX_RECEIPT_BYTES,
    MAX_SNAPSHOT_BYTES,
    load_json,
    pretty_json,
)
from featureseal.engine import analyze_document
from featureseal.errors import FeatureSealError
from featureseal.report import render_report
from featureseal.verify import verify_receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="featureseal",
        description="Analyze and independently replay bounded point-in-time feature joins.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    analyze = commands.add_parser("analyze", help="create a deterministic join receipt")
    analyze.add_argument("snapshot", type=Path)
    analyze.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify", help="replay a receipt with SQLite")
    verify.add_argument("receipt", type=Path)

    inspect = commands.add_parser("inspect", help="print bounded join findings")
    inspect.add_argument("receipt", type=Path)

    report = commands.add_parser("report", help="render a self-contained HTML report")
    report.add_argument("receipt", type=Path)
    report.add_argument("--output", type=Path, required=True)
    return parser


def _write_new(path: Path, content: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise FeatureSealError(f"refusing to replace existing file: {path}") from exc
    except OSError as exc:
        raise FeatureSealError(f"cannot write {path}") from exc


def _load_receipt(path: Path) -> dict[str, object]:
    document = load_json(path, max_bytes=MAX_RECEIPT_BYTES)
    verify_receipt(document)
    return cast(dict[str, object], document)


def _analyze(snapshot_path: Path, output: Path) -> None:
    document = load_json(snapshot_path, max_bytes=MAX_SNAPSHOT_BYTES)
    receipt = analyze_document(document)
    _write_new(output, pretty_json(receipt))
    summary = cast(dict[str, object], receipt["summary"])
    print(
        f"analyzed {summary['events']} events / {summary['observations']} observations / "
        f"{summary['cells']} join cells"
    )
    print(
        f"findings {summary['finding_cells']}; matched cells {summary['matched_cells']}"
    )
    print(f"snapshot sha256 {receipt['snapshot_sha256']}")
    print(f"ledger root    {receipt['ledger_root_sha256']}")
    print(f"receipt sha256 {receipt['receipt_sha256']}")


def _verify(path: Path) -> None:
    receipt = _load_receipt(path)
    summary = cast(dict[str, object], receipt["summary"])
    print(
        f"verified {summary['cells']} cells with SQLite; "
        f"{summary['finding_cells']} findings; {summary['matched_cells']} matched"
    )
    print(f"ledger root    {receipt['ledger_root_sha256']}")
    print(f"receipt sha256 {receipt['receipt_sha256']}")


def _inspect(path: Path) -> None:
    receipt = _load_receipt(path)
    findings = cast(list[dict[str, object]], receipt["findings"])
    print(
        "ID               RULE                 OBSERVATION   FEATURE        "
        "SELECTED      EXPECTED"
    )
    print("-" * 94)
    for finding in findings:
        print(
            f"{finding['finding_id']!s:<16} {finding['rule']!s:<20} "
            f"{finding['observation_id']!s:<13} {finding['feature']!s:<14} "
            f"{(finding['selected_event'] or '∅')!s:<13} "
            f"{(finding['expected_event'] or '∅')!s}"
        )


def _report(path: Path, output: Path) -> None:
    receipt = _load_receipt(path)
    _write_new(output, render_report(receipt))
    print(f"wrote verified report {output}")
    print(f"receipt sha256 {receipt['receipt_sha256']}")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "analyze":
            _analyze(arguments.snapshot, arguments.output)
        elif arguments.command == "verify":
            _verify(arguments.receipt)
        elif arguments.command == "inspect":
            _inspect(arguments.receipt)
        else:
            _report(arguments.receipt, arguments.output)
    except (FeatureSealError, OSError) as exc:
        print(f"featureseal: {exc}", file=sys.stderr)
        return 2
    return 0
