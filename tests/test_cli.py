"""Installed-style CLI and report workflow tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import SCENARIO

from featureseal.cli import main


def test_complete_cli_workflow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    receipt = tmp_path / "receipt.json"
    report = tmp_path / "report.html"

    assert main(["analyze", str(SCENARIO), "--output", str(receipt)]) == 0
    output = capsys.readouterr().out
    assert "analyzed 18 events / 7 observations / 28 join cells" in output
    assert "findings 6; matched cells 22" in output

    assert main(["verify", str(receipt)]) == 0
    assert "verified 28 cells with SQLite; 6 findings; 22 matched" in capsys.readouterr().out

    assert main(["inspect", str(receipt)]) == 0
    inspected = capsys.readouterr().out
    assert inspected.count("FS-") == 6
    assert "FUTURE_EVENT" in inspected
    assert "UNAVAILABLE_EVENT" in inspected
    assert "IDENTITY_MISMATCH" in inspected

    assert main(["report", str(receipt), "--output", str(report)]) == 0
    assert "wrote verified report" in capsys.readouterr().out
    html = report.read_text(encoding="utf-8")
    assert "Point-in-time features" in html
    assert "Bounded join findings" in html
    assert "SQLite verifier passed" in html
    assert "synthetic fixture" in html
    assert "Minimal" not in html
    assert str(tmp_path) not in html


def test_analyze_refuses_to_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "receipt.json"
    output.write_text("occupied", encoding="utf-8")
    assert main(["analyze", str(SCENARIO), "--output", str(output)]) == 2
    assert "refusing to replace" in capsys.readouterr().err
    assert output.read_text(encoding="utf-8") == "occupied"


def test_report_refuses_to_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = tmp_path / "receipt.json"
    report = tmp_path / "report.html"
    assert main(["analyze", str(SCENARIO), "--output", str(receipt)]) == 0
    capsys.readouterr()
    report.write_text("occupied", encoding="utf-8")
    assert main(["report", str(receipt), "--output", str(report)]) == 2
    assert "refusing to replace" in capsys.readouterr().err
    assert report.read_text(encoding="utf-8") == "occupied"


def test_invalid_json_returns_bounded_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "bad.json"
    source.write_text("{", encoding="utf-8")
    assert main(["analyze", str(source), "--output", str(tmp_path / "out.json")]) == 2
    assert "invalid JSON document" in capsys.readouterr().err


def test_verify_rejects_tampered_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "not-receipt.json"
    source.write_text('{"format":"wrong"}', encoding="utf-8")
    assert main(["verify", str(source)]) == 2
    assert "receipt format" in capsys.readouterr().err
