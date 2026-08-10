"""Generate and verify source-bound FeatureSeal portfolio evidence."""

# ruff: noqa: E501 -- deterministic SVG, CSS, and evidence contracts stay reviewable

from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
import struct
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, cast

FORMAT = "featureseal.evidence.v1"
EVIDENCE_DIRECTORY = Path("docs/evidence")
MANIFEST_NAME = "featureseal-evidence.json"
CONTAINER_IMAGE = (
    "mcr.microsoft.com/playwright/python@"
    "sha256:51d31fdfacb0cff99a1a724152e34ae408d2bd4e7da310ff157450f49261cc59"
)
EXPECTED_FILES = {
    "architecture.svg",
    "featureseal-cli.png",
    "featureseal-cli.txt",
    "featureseal-demo.gif",
    "featureseal-receipt.json",
    "featureseal-report-full.png",
    "featureseal-report-mobile.png",
    "featureseal-report.html",
    "featureseal-report.png",
    "temporal-contract.svg",
    "finding-distribution.svg",
    "availability-timeline.svg",
}
MEDIA_TYPES = {
    ".gif": "image/gif",
    ".html": "text/html",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
}
FORBIDDEN_TEXT = (
    "/home/",
    "/Users/",
    "github_pat_",
    "gho_",
    "ghp_",
    "sk-proj-",
    "BEGIN PRIVATE KEY",
    "Authorization: Bearer",
    "api.telegram.org/bot",
    "xoxb-",
    "AKIA",
)
RULE_LABELS = {
    "FUTURE_EVENT": "Future event",
    "UNAVAILABLE_EVENT": "Unavailable event",
    "IDENTITY_MISMATCH": "Identity mismatch",
    "EXPIRED_EVENT": "Expired event",
    "STALE_SELECTION": "Stale selection",
    "MISSING_SELECTION": "Missing selection",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--root", type=Path, required=True)
    prepare_parser.add_argument("--receipt", type=Path, required=True)
    prepare_parser.add_argument("--report", type=Path, required=True)
    prepare_parser.add_argument("--cli", type=Path, required=True)
    prepare_parser.add_argument("--output-root", type=Path, required=True)

    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--output-root", type=Path, required=True)
    capture_parser.add_argument("--container-image", required=True)

    finalize_parser = commands.add_parser("finalize")
    finalize_parser.add_argument("--root", type=Path, required=True)
    finalize_parser.add_argument("--output-root", type=Path, required=True)
    finalize_parser.add_argument("--source-revision", required=True)
    finalize_parser.add_argument("--source-tree", required=True)
    finalize_parser.add_argument("--container-image", required=True)
    finalize_parser.add_argument("--browser", required=True)
    finalize_parser.add_argument("--playwright", required=True)
    finalize_parser.add_argument("--pillow", required=True)

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, required=True)
    verify_parser.add_argument("--output-root", type=Path, required=True)
    verify_parser.add_argument("--source-revision", required=True)
    verify_parser.add_argument("--source-tree", required=True)
    verify_parser.add_argument("--container-image", required=True)

    visual_parser = commands.add_parser("verify-visuals")
    visual_parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "prepare":
        prepare(
            arguments.root,
            arguments.receipt,
            arguments.report,
            arguments.cli,
            arguments.output_root,
        )
    elif arguments.command == "capture":
        capture(arguments.output_root, arguments.container_image)
    elif arguments.command == "finalize":
        finalize(
            arguments.root,
            arguments.output_root,
            arguments.source_revision,
            arguments.source_tree,
            arguments.container_image,
            arguments.browser,
            arguments.playwright,
            arguments.pillow,
        )
    elif arguments.command == "verify":
        verify(
            arguments.root,
            arguments.output_root,
            arguments.source_revision,
            arguments.source_tree,
            arguments.container_image,
        )
    else:
        verify_visuals(arguments.output_root)
    return 0


def prepare(
    root: Path,
    receipt_path: Path,
    report_path: Path,
    cli_path: Path,
    output_root: Path,
) -> None:
    root = root.resolve()
    if output_root.exists():
        raise ValueError("evidence output root already exists")
    evidence = output_root / EVIDENCE_DIRECTORY
    evidence.mkdir(parents=True)

    from featureseal.canonical import MAX_RECEIPT_BYTES, load_json, pretty_json
    from featureseal.report import render_report
    from featureseal.verify import verify_receipt

    document = load_json(receipt_path, max_bytes=MAX_RECEIPT_BYTES)
    if not isinstance(document, dict):
        raise ValueError("evidence receipt must be an object")
    receipt = cast(dict[str, object], document)
    summary = verify_receipt(receipt)
    report = report_path.read_text(encoding="utf-8")
    if report != render_report(receipt):
        raise ValueError("CLI report differs from verified library rendering")
    cli = cli_path.read_text(encoding="utf-8")
    _reject_sensitive_text(cli)
    if not cli.startswith("$ featureseal analyze snapshot.json --output receipt.json"):
        raise ValueError("CLI transcript does not begin with the executed analyze command")
    if str(receipt["receipt_sha256"]) not in cli:
        raise ValueError("CLI transcript does not expose the receipt digest")
    if (
        f"verified {summary['cells']} cells with SQLite; "
        f"{summary['finding_cells']} findings; {summary['matched_cells']} matched" not in cli
    ):
        raise ValueError("CLI transcript does not include independent replay")

    _write_text(evidence / "featureseal-receipt.json", pretty_json(receipt))
    _write_text(evidence / "featureseal-report.html", report)
    _write_text(evidence / "featureseal-cli.txt", cli)
    _write_text(evidence / "architecture.svg", _architecture_svg(receipt))
    _write_text(evidence / "temporal-contract.svg", _temporal_contract_svg(receipt))
    _write_text(evidence / "availability-timeline.svg", _availability_timeline_svg(receipt))
    _write_text(evidence / "finding-distribution.svg", _distribution_svg(receipt))
    _write_text(output_root / "terminal.html", _terminal_html(cli))


def capture(output_root: Path, container_image: str) -> None:
    if container_image != CONTAINER_IMAGE:
        raise ValueError("unpinned evidence container")
    from PIL import Image
    from playwright.sync_api import sync_playwright

    evidence = output_root / EVIDENCE_DIRECTORY
    report_uri = (evidence / "featureseal-report.html").resolve().as_uri()
    terminal_uri = (output_root / "terminal.html").resolve().as_uri()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        desktop = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        page = desktop.new_page()
        page.goto(report_uri, wait_until="load")
        page.screenshot(path=evidence / "featureseal-report.png")
        page.screenshot(path=evidence / "featureseal-report-full.png", full_page=True)
        desktop.close()

        mobile = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        page = mobile.new_page()
        page.goto(report_uri, wait_until="load")
        page.screenshot(path=evidence / "featureseal-report-mobile.png")
        mobile.close()

        terminal = browser.new_context(
            viewport={"width": 1180, "height": 650},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        page = terminal.new_page()
        page.goto(terminal_uri, wait_until="load")
        page.screenshot(path=evidence / "featureseal-cli.png")
        terminal.close()

        demo = browser.new_context(
            viewport={"width": 1120, "height": 820},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        page = demo.new_page()
        page.goto(report_uri, wait_until="load")
        frames = []
        for selector in ("header", "#findings", "#receipt"):
            page.locator(selector).scroll_into_view_if_needed()
            image = Image.open(BytesIO(page.screenshot())).convert("RGB")
            frames.append(
                image.quantize(
                    colors=128,
                    method=Image.Quantize.MEDIANCUT,
                    dither=Image.Dither.NONE,
                )
            )
        frames[0].save(
            evidence / "featureseal-demo.gif",
            save_all=True,
            append_images=frames[1:],
            duration=(1400, 1700, 1700),
            loop=0,
            disposal=2,
            optimize=False,
        )
        demo.close()
        browser.close()


def finalize(
    root: Path,
    output_root: Path,
    source_revision: str,
    source_tree: str,
    container_image: str,
    browser: str,
    playwright: str,
    pillow: str,
) -> None:
    _validate_oid(source_revision, "source revision")
    _validate_oid(source_tree, "source tree")
    if container_image != CONTAINER_IMAGE:
        raise ValueError("evidence container mismatch")
    evidence = output_root / EVIDENCE_DIRECTORY
    receipt = json.loads((evidence / "featureseal-receipt.json").read_text(encoding="utf-8"))
    from featureseal.verify import verify_receipt

    summary = verify_receipt(receipt)
    manifest = {
        "format": FORMAT,
        "source_revision": source_revision,
        "source_tree": source_tree,
        "generation": {
            "container_image": container_image,
            "browser": browser,
            "playwright": playwright,
            "pillow": pillow,
            "python": platform.python_version(),
            "network": "disabled during browser capture",
            "filesystem": "read-only source mount",
        },
        "snapshot_sha256": receipt["snapshot_sha256"],
        "ledger_root_sha256": receipt["ledger_root_sha256"],
        "receipt_sha256": receipt["receipt_sha256"],
        "result": _result(summary),
        "sources": [_file_record(path, root) for path in _source_paths(root)],
        "files": [
            _evidence_record(path, output_root)
            for path in sorted(evidence.iterdir())
            if path.name != MANIFEST_NAME
        ],
    }
    _write_text(
        evidence / MANIFEST_NAME,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def verify(
    root: Path,
    output_root: Path,
    source_revision: str,
    source_tree: str,
    container_image: str,
) -> None:
    _validate_oid(source_revision, "source revision")
    _validate_oid(source_tree, "source tree")
    evidence = output_root / EVIDENCE_DIRECTORY
    actual = {path.name for path in evidence.iterdir() if path.is_file()}
    expected = EXPECTED_FILES | {MANIFEST_NAME}
    if actual != expected:
        raise ValueError(f"evidence file set differs: {sorted(actual ^ expected)}")
    manifest = json.loads((evidence / MANIFEST_NAME).read_text(encoding="utf-8"))
    if manifest["format"] != FORMAT:
        raise ValueError("evidence format mismatch")
    if manifest["source_revision"] != source_revision or manifest["source_tree"] != source_tree:
        raise ValueError("evidence source binding mismatch")
    if manifest["generation"]["container_image"] != container_image:
        raise ValueError("evidence container mismatch")
    if manifest["generation"]["python"] != "3.14.6":
        raise ValueError("evidence Python runtime mismatch")
    if manifest["sources"] != [_file_record(path, root) for path in _source_paths(root)]:
        raise ValueError("evidence source hashes differ")
    expected_files = [
        _evidence_record(path, output_root)
        for path in sorted(evidence.iterdir())
        if path.name != MANIFEST_NAME
    ]
    if manifest["files"] != expected_files:
        raise ValueError("evidence file hashes or dimensions differ")

    from featureseal.canonical import MAX_RECEIPT_BYTES, load_json
    from featureseal.report import render_report
    from featureseal.verify import verify_receipt

    document = load_json(
        evidence / "featureseal-receipt.json",
        max_bytes=MAX_RECEIPT_BYTES,
    )
    if not isinstance(document, dict):
        raise ValueError("evidence receipt must be an object")
    receipt = cast(dict[str, object], document)
    summary = verify_receipt(receipt)
    if (evidence / "featureseal-report.html").read_text(encoding="utf-8") != render_report(receipt):
        raise ValueError("checked-in report does not replay")
    if manifest["result"] != _result(summary):
        raise ValueError("manifest result does not match independent replay")
    for key in ("snapshot_sha256", "ledger_root_sha256", "receipt_sha256"):
        if manifest[key] != receipt[key]:
            raise ValueError(f"manifest {key} mismatch")

    for path in evidence.iterdir():
        if path.suffix in {".html", ".json", ".svg", ".txt"}:
            _reject_sensitive_text(path.read_text(encoding="utf-8"))
        if path.suffix == ".svg":
            _verify_svg(path)


def verify_visuals(output_root: Path) -> None:
    from PIL import Image, ImageSequence

    evidence = output_root / EVIDENCE_DIRECTORY
    expected_png = {
        "featureseal-report.png": (1440, 1000),
        "featureseal-report-mobile.png": (390, 844),
        "featureseal-cli.png": (1180, 650),
    }
    for name, dimensions in expected_png.items():
        with Image.open(evidence / name) as image:
            if image.format != "PNG" or image.size != dimensions:
                raise ValueError(
                    f"unexpected raster contract for {name}: {image.format} {image.size}"
                )
            _reject_blank_image(image, name)
    with Image.open(evidence / "featureseal-report-full.png") as image:
        if image.format != "PNG" or image.width != 1440 or image.height < 1_800:
            raise ValueError(f"unexpected full-page raster: {image.format} {image.size}")
        _reject_blank_image(image, "featureseal-report-full.png")
    with Image.open(evidence / "featureseal-demo.gif") as image:
        frames = [frame.convert("RGB") for frame in ImageSequence.Iterator(image)]
        if image.format != "GIF" or image.size != (1120, 820) or len(frames) != 3:
            raise ValueError(f"unexpected GIF contract: {image.format} {image.size} {len(frames)}")
        digests = set()
        for index, frame in enumerate(frames):
            _reject_blank_image(frame, f"featureseal-demo.gif frame {index}")
            digests.add(hashlib.sha256(frame.tobytes()).hexdigest())
        if len(digests) != 3:
            raise ValueError("GIF frames are not visually distinct")


def _reject_blank_image(image: Any, label: str) -> None:
    converted = image.convert("RGB")
    extrema = converted.getextrema()
    if all(low == high for low, high in extrema):
        raise ValueError(f"blank evidence image: {label}")
    colors = converted.resize((160, 100)).getcolors(maxcolors=20_000)
    if colors is None or len(colors) < 12:
        raise ValueError(f"insufficient visual detail: {label}")


def _result(summary: dict[str, object]) -> dict[str, object]:
    keys = (
        "features",
        "events",
        "observations",
        "entities",
        "cells",
        "matched_cells",
        "finding_cells",
        "rule_counts",
    )
    return {key: summary[key] for key in keys}


def _architecture_svg(receipt: dict[str, object]) -> str:
    summary = cast(dict[str, object], receipt["summary"])
    stages = (
        ("01", "SNAPSHOT CONTRACT", f"{summary['features']} typed features · strict JSON"),
        ("02", "INDEXED JOIN", f"{summary['events']} events · reverse scans"),
        ("03", "PRIMARY REASONS", f"{summary['finding_cells']} bounded mismatches"),
        ("04", "HASHED RECEIPT", f"{summary['cells']} cells · 35 ledger entries"),
        ("05", "SQLITE REPLAY", f"{summary['matched_cells']} exact matches"),
    )
    boxes = []
    for index, (number, title, detail) in enumerate(stages):
        x = 42 + index * 231
        stroke = "#ffb454" if index == 2 else "#65ded7"
        boxes.append(
            f"""<g transform="translate({x} 170)">
<rect width="198" height="194" rx="24" fill="#182445" stroke="{stroke}" stroke-width="2"/>
<text x="20" y="36" fill="#83eee5" font-size="13" font-weight="800">{number}</text>
<text x="20" y="79" fill="#ffffff" font-size="14" font-weight="800">{html.escape(title)}</text>
<text x="20" y="119" fill="#c7d3eb" font-size="12">{html.escape(detail)}</text>
</g>"""
        )
    arrows = "".join(
        f'<path d="M {240 + index * 231} 267 H {274 + index * 231}" stroke="#83eee5" stroke-width="3" marker-end="url(#arrow)"/>'
        for index in range(4)
    )
    snapshot_digest = html.escape(str(receipt["snapshot_sha256"])[:18])
    ledger_digest = html.escape(str(receipt["ledger_root_sha256"])[:18])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 530">
<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#0b1022"/><stop offset="1" stop-color="#253168"/></linearGradient><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0L6 3L0 6Z" fill="#83eee5"/></marker></defs>
<rect width="1200" height="530" rx="28" fill="url(#bg)"/>
<text x="42" y="60" fill="#83eee5" font-size="14" font-weight="800" letter-spacing="2">FEATURESEAL / DUAL-ALGORITHM WORKFLOW</text>
<text x="42" y="108" fill="#ffffff" font-size="34" font-weight="800">Point-in-time joins become replayable evidence</text>
{"".join(boxes)}{arrows}
<text x="42" y="438" fill="#b8c7e0" font-size="13">Snapshot {snapshot_digest}… · Ledger {ledger_digest}…</text>
<text x="42" y="474" fill="#e5eaf6" font-size="14">The analyzer uses indexed reverse scans; the verifier independently queries in-memory SQLite.</text>
</svg>
"""


def _temporal_contract_svg(receipt: dict[str, object]) -> str:
    snapshot = cast(dict[str, object], receipt["snapshot"])
    events = cast(list[dict[str, object]], snapshot["events"])
    findings = cast(list[dict[str, object]], receipt["findings"])
    finding = next(item for item in findings if item["rule"] == "UNAVAILABLE_EVENT")
    by_id = {str(event["event_id"]): event for event in events}
    selected = by_id[str(finding["selected_event"])]
    expected = by_id[str(finding["expected_event"])]
    observation_at = int(finding["at"])

    def xpos(value: int) -> int:
        return 120 + int(value / 1000 * 940)

    event_x = xpos(int(selected["event_time"]))
    availability_x = xpos(int(selected["available_time"]))
    observation_x = xpos(observation_at)
    expected_x = xpos(int(expected["event_time"]))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 560">
<defs><linearGradient id="bg2" x2="1"><stop stop-color="#f7f8ff"/><stop offset="1" stop-color="#eef9f8"/></linearGradient><marker id="tip" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0L6 3L0 6Z" fill="#59677f"/></marker></defs>
<rect width="1200" height="560" rx="28" fill="url(#bg2)"/>
<text x="58" y="62" fill="#7857ed" font-size="14" font-weight="800" letter-spacing="2">REAL WITNESS / {html.escape(str(finding["finding_id"]))}</text>
<text x="58" y="108" fill="#18243a" font-size="33" font-weight="800">Event time is not availability time</text>
<text x="58" y="142" fill="#66758b" font-size="14">{html.escape(str(finding["observation_id"]))} · {html.escape(str(finding["feature"]))} · selected {html.escape(str(selected["event_id"]))}</text>
<line x1="120" y1="272" x2="1060" y2="272" stroke="#aab4c7" stroke-width="3" marker-end="url(#tip)"/>
<line x1="{event_x}" y1="233" x2="{availability_x}" y2="233" stroke="#e9a63a" stroke-width="8" stroke-linecap="round"/>
<circle cx="{event_x}" cy="272" r="13" fill="#43c8cf"/><circle cx="{availability_x}" cy="272" r="13" fill="#e9a63a"/>
<line x1="{observation_x}" y1="190" x2="{observation_x}" y2="352" stroke="#e85e72" stroke-width="4" stroke-dasharray="9 7"/>
<circle cx="{expected_x}" cy="272" r="10" fill="#16846f"/>
<text x="{event_x}" y="206" text-anchor="middle" fill="#273550" font-size="13" font-weight="800">event_time {html.escape(str(selected["event_time"]))}</text>
<text x="{availability_x}" y="206" text-anchor="middle" fill="#9a6817" font-size="13" font-weight="800">available {html.escape(str(selected["available_time"]))}</text>
<text x="{observation_x}" y="378" text-anchor="middle" fill="#b83e54" font-size="13" font-weight="800">observation {observation_at}</text>
<text x="{expected_x}" y="315" text-anchor="middle" fill="#126b5c" font-size="12">eligible {html.escape(str(expected["event_id"]))}</text>
<text x="58" y="445" fill="#18243a" font-size="18" font-weight="800">Why it is flagged</text>
<text x="58" y="477" fill="#59677f" font-size="14">{html.escape(str(finding["explanation"]))}</text>
<text x="58" y="515" fill="#59677f" font-size="13">Selection is replayed with both event_time ≤ observation and available_time ≤ observation.</text>
</svg>
"""


def _availability_timeline_svg(receipt: dict[str, object]) -> str:
    snapshot = cast(dict[str, object], receipt["snapshot"])
    events = cast(list[dict[str, object]], snapshot["events"])
    features = cast(list[dict[str, object]], snapshot["features"])
    observations = cast(list[dict[str, object]], snapshot["observations"])
    entities = sorted({str(event["entity"]) for event in events})
    feature_names = [str(feature["name"]) for feature in features]
    rows = [(entity, feature) for entity in entities for feature in feature_names]
    row_index = {row: index for index, row in enumerate(rows)}

    def xpos(value: int) -> int:
        return 230 + int(value / 1000 * 900)

    grid = []
    for tick in (0, 250, 500, 750, 1000):
        x = xpos(tick)
        grid.append(
            f'<line x1="{x}" y1="130" x2="{x}" y2="705" stroke="#dce2ee"/><text x="{x}" y="112" text-anchor="middle" fill="#718096" font-size="11">{tick}</text>'
        )
    labels = []
    for index, (entity, feature) in enumerate(rows):
        y = 154 + index * 44
        labels.append(
            f'<text x="48" y="{y + 4}" fill="#26344e" font-size="11"><tspan font-weight="800">{html.escape(entity)}</tspan><tspan x="118">{html.escape(feature)}</tspan></text><line x1="230" y1="{y}" x2="1130" y2="{y}" stroke="#edf0f6"/>'
        )
    marks = []
    for event in events:
        y = 154 + row_index[(str(event["entity"]), str(event["feature"]))] * 44
        start = xpos(int(event["event_time"]))
        end = xpos(int(event["available_time"]))
        late = end > start
        color = "#e9a63a" if late else "#43c8cf"
        marks.append(
            f'<line x1="{start}" y1="{y}" x2="{max(start + 2, end)}" y2="{y}" stroke="{color}" stroke-width="7" stroke-linecap="round"/><circle cx="{start}" cy="{y}" r="5" fill="#7857ed"/><text x="{max(start, end) + 7}" y="{y - 7}" fill="#42526d" font-size="9">{html.escape(str(event["event_id"]))}</text>'
        )
    late_count = sum(int(event["available_time"]) > int(event["event_time"]) for event in events)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 760">
<rect width="1200" height="760" rx="28" fill="#ffffff"/>
<text x="48" y="55" fill="#7857ed" font-size="14" font-weight="800" letter-spacing="2">SOURCE-DERIVED AVAILABILITY MAP</text>
<text x="48" y="91" fill="#18243a" font-size="27" font-weight="800">{len(events)} events · {len(observations)} observation snapshots · {late_count} late arrivals</text>
{"".join(grid)}{"".join(labels)}{"".join(marks)}
<rect x="48" y="718" width="12" height="12" rx="6" fill="#43c8cf"/><text x="68" y="728" fill="#66758b" font-size="11">on-time</text>
<rect x="145" y="718" width="12" height="12" rx="6" fill="#e9a63a"/><text x="165" y="728" fill="#66758b" font-size="11">availability lag</text>
<circle cx="285" cy="724" r="5" fill="#7857ed"/><text x="298" y="728" fill="#66758b" font-size="11">event time</text>
</svg>
"""


def _distribution_svg(receipt: dict[str, object]) -> str:
    summary = cast(dict[str, object], receipt["summary"])
    counts = cast(dict[str, int], summary["rule_counts"])
    maximum = max(1, max(counts.values()))
    rows = []
    for index, (rule, label) in enumerate(RULE_LABELS.items()):
        y = 176 + index * 58
        width = int(470 * counts[rule] / maximum)
        rows.append(
            f'<text x="55" y="{y + 5}" fill="#273550" font-size="13">{html.escape(label)}</text>'
            f'<rect x="225" y="{y - 13}" width="470" height="20" rx="10" fill="#edf0f6"/>'
            f'<rect x="225" y="{y - 13}" width="{width}" height="20" rx="10" fill="url(#bar)"/>'
            f'<text x="712" y="{y + 5}" fill="#18243a" font-size="13" font-weight="800">{counts[rule]}</text>'
        )
    finding_cells = int(summary["finding_cells"])
    cells = int(summary["cells"])
    matched = int(summary["matched_cells"])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 590">
<defs><linearGradient id="bar"><stop stop-color="#7857ed"/><stop offset="1" stop-color="#43c8cf"/></linearGradient></defs>
<rect width="1200" height="590" rx="28" fill="#f7f8fc"/>
<text x="55" y="58" fill="#7857ed" font-size="14" font-weight="800" letter-spacing="2">PRIMARY REASON DISTRIBUTION</text>
<text x="55" y="101" fill="#18243a" font-size="31" font-weight="800">Every mismatched cell gets one reason</text>
{"".join(rows)}
<rect x="790" y="148" width="350" height="300" rx="26" fill="#11182d"/>
<text x="830" y="198" fill="#78e5df" font-size="13" font-weight="800">REFERENCE SCENARIO</text>
<text x="830" y="268" fill="#ffffff" font-size="57" font-weight="800">{matched}</text>
<text x="830" y="300" fill="#cbd5e8" font-size="14">matched cells</text>
<text x="830" y="364" fill="#ff9aac" font-size="38" font-weight="800">{finding_cells}</text>
<text x="920" y="364" fill="#cbd5e8" font-size="14">findings / {cells} total</text>
<text x="55" y="528" fill="#66758b" font-size="13">Counts describe the checked-in synthetic fixture—not a production leakage rate.</text>
</svg>
"""


def _terminal_html(cli: str) -> str:
    escaped = html.escape(cli)
    return f"""<!doctype html><meta charset="utf-8"><style>
html,body{{margin:0;background:#071019;color:#dce8f2}}body{{padding:34px;font:15px/1.48 ui-monospace,SFMono-Regular,Consolas,monospace}}
.window{{border:1px solid #294158;border-radius:18px;overflow:hidden;box-shadow:0 24px 70px #0008}}
.bar{{height:46px;background:#101e2c;border-bottom:1px solid #294158;display:flex;align-items:center;padding:0 18px;gap:9px}}
.dot{{width:12px;height:12px;border-radius:50%}}.r{{background:#ff6b6b}}.y{{background:#f4d35e}}.g{{background:#52d6a6}}
pre{{margin:0;padding:24px 28px;white-space:pre-wrap;overflow-wrap:anywhere}}
</style><div class="window"><div class="bar"><i class="dot r"></i><i class="dot y"></i><i class="dot g"></i></div><pre>{escaped}</pre></div>"""


def _source_paths(root: Path) -> list[Path]:
    paths = [
        root / ".github/workflows/evidence.yml",
        root / "pyproject.toml",
        root / "requirements/evidence-browser-image.lock.json",
        root / "requirements/evidence-browser.txt",
        root / "requirements/quality.in",
        root / "requirements/quality.txt",
        root / "scenarios/late-feature-incident.json",
        root / "tools/capture_evidence.py",
    ]
    paths.extend(sorted((root / "src/featureseal").glob("*.py")))
    paths.append(root / "src/featureseal/py.typed")
    return paths


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _evidence_record(path: Path, root: Path) -> dict[str, Any]:
    record = _file_record(path, root)
    record["media_type"] = MEDIA_TYPES[path.suffix]
    if path.suffix == ".png":
        record["dimensions"] = list(_png_dimensions(path))
    elif path.suffix == ".gif":
        record["dimensions"] = list(_gif_dimensions(path))
        record["frames"] = 3
    return record


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"invalid PNG: {path}")
    return struct.unpack(">II", data[16:24])


def _gif_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:10]
    if len(data) != 10 or data[:6] not in {b"GIF87a", b"GIF89a"}:
        raise ValueError(f"invalid GIF: {path}")
    return struct.unpack("<HH", data[6:10])


def _validate_oid(value: str, label: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"invalid {label}")


def _verify_svg(path: Path) -> None:
    root = ET.parse(path).getroot()
    if not root.tag.endswith("svg") or root.get("viewBox") is None:
        raise ValueError(f"invalid SVG structure: {path}")
    if len(list(root.iter())) < 8:
        raise ValueError(f"SVG lacks detail: {path}")


def _reject_sensitive_text(value: str) -> None:
    for marker in FORBIDDEN_TEXT:
        if marker in value:
            raise ValueError(f"evidence contains forbidden marker: {marker}")


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
