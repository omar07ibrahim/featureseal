"""Render a source-free, self-contained point-in-time join report."""

from __future__ import annotations

import html
from typing import cast

from featureseal.verify import verify_receipt

_RULE_LABELS = {
    "FUTURE_EVENT": "Future event",
    "UNAVAILABLE_EVENT": "Unavailable event",
    "IDENTITY_MISMATCH": "Identity mismatch",
    "EXPIRED_EVENT": "Expired event",
    "STALE_SELECTION": "Stale selection",
    "MISSING_SELECTION": "Missing selection",
}


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_report(receipt: dict[str, object]) -> str:
    """Verify first, then render only canonical receipt fields."""

    summary = verify_receipt(receipt)
    snapshot = cast(dict[str, object], receipt["snapshot"])
    events = cast(list[dict[str, object]], snapshot["events"])
    cells = cast(list[dict[str, object]], receipt["cells"])
    findings = cast(list[dict[str, object]], receipt["findings"])
    counts = cast(dict[str, int], summary["rule_counts"])
    maximum = max(1, max(counts.values()))

    metrics = (
        ("Events", summary["events"], "typed updates"),
        ("Join cells", summary["cells"], "point-in-time"),
        ("Findings", summary["finding_cells"], "primary reasons"),
        ("Matched", summary["matched_cells"], "exact parity"),
    )
    metric_cards = "".join(
        f"""<article class="metric"><span>{_escape(label)}</span>
<strong>{_escape(value)}</strong><small>{_escape(note)}</small></article>"""
        for label, value, note in metrics
    )
    bars = "".join(
        f"""<div class="bar-row"><span>{_escape(_RULE_LABELS[rule])}</span>
<div class="track"><i style="width:{100 * count / maximum:.1f}%"></i></div>
<strong>{count}</strong></div>"""
        for rule, count in counts.items()
    )
    timeline = "".join(
        f"""<div class="tick {"late" if cast(int, event["available_time"]) > cast(int, event["event_time"]) else "ontime"}">
<span>{_escape(event["event_time"])} → {_escape(event["available_time"])}</span>
<b>{_escape(event["event_id"])}</b>
<small>{_escape(event["entity"])} · {_escape(event["feature"])}</small></div>"""
        for event in events
    )
    finding_rows = "".join(
        f"""<tr><td><code>{_escape(item["finding_id"])}</code></td>
<td><span class="rule">{_escape(_RULE_LABELS[str(item["rule"])])}</span></td>
<td><code>{_escape(item["observation_id"])}</code></td>
<td>{_escape(item["feature"])}</td>
<td><code>{_escape(item["selected_event"] or "∅")}</code></td>
<td><code>{_escape(item["expected_event"] or "∅")}</code></td>
<td>{_escape(item["explanation"])}</td></tr>"""
        for item in findings
    )
    cell_rows = "".join(
        f"""<tr><td><code>{_escape(cell["observation_id"])}</code></td>
<td>{_escape(cell["at"])}</td><td>{_escape(cell["entity"])}</td>
<td>{_escape(cell["feature"])}</td>
<td><code>{_escape(cell["selected_event"] or "∅")}</code></td>
<td><code>{_escape(cell["expected_event"] or "∅")}</code></td>
<td><span class="status {"match" if cell["status"] == "MATCH" else "finding"}">{_escape(cell["status"])}</span></td></tr>"""
        for cell in cells
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FeatureSeal · {_escape(snapshot["snapshot_id"])}</title>
<style>
:root{{--ink:#18243a;--muted:#66758b;--paper:#f4f6fb;--card:#fff;--night:#10162a;
--violet:#7857ed;--cyan:#43c8cf;--red:#e85e72;--amber:#e9a63a;--green:#16846f;--line:#dfe5ef}}
*{{box-sizing:border-box}}html{{background:var(--paper);color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}
body{{margin:0}}header{{background:radial-gradient(circle at 82% 0,#43358b 0,transparent 38%),linear-gradient(140deg,#0d1325,#1c2744);color:#fff;padding:54px max(5vw,28px) 50px}}
.eyebrow{{color:#77e2e1;font-size:12px;font-weight:800;letter-spacing:.18em;text-transform:uppercase}}
h1{{font-size:clamp(38px,6vw,72px);line-height:1;margin:14px 0 18px;letter-spacing:-.045em}}
.lead{{max-width:850px;color:#ced7eb;font-size:18px}}.badges{{display:flex;gap:10px;flex-wrap:wrap;margin-top:26px}}
.badge{{border:1px solid #ffffff2d;border-radius:99px;padding:7px 12px;background:#ffffff0d;color:#e0e8f8;font-size:12px}}
main{{max-width:1240px;margin:auto;padding:32px 28px 70px}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:-68px}}
.metric{{background:var(--card);border:1px solid var(--line);box-shadow:0 18px 44px #233d5a12;border-radius:18px;padding:22px}}
.metric span,.metric small{{display:block;color:var(--muted)}}.metric strong{{display:block;font-size:36px;line-height:1.1;margin:8px 0;color:var(--night)}}
section{{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:26px;margin-top:22px;overflow:hidden}}
h2{{font-size:24px;margin:0 0 6px;letter-spacing:-.02em}}.sub{{color:var(--muted);margin:0 0 22px}}
.overview{{display:grid;grid-template-columns:1.1fr .9fr;gap:22px}}.overview section{{margin:0}}
.bar-row{{display:grid;grid-template-columns:150px 1fr 28px;align-items:center;gap:12px;margin:12px 0}}
.track{{height:11px;background:#edf0f6;border-radius:99px;overflow:hidden}}.track i{{display:block;height:100%;background:linear-gradient(90deg,var(--violet),var(--cyan));border-radius:99px}}
.timeline{{display:grid;grid-template-columns:repeat(6,1fr);gap:9px}}.tick{{border:1px solid var(--line);border-top:4px solid var(--cyan);border-radius:12px;padding:10px;min-width:0}}
.tick.late{{border-top-color:var(--amber);background:#fffaf1}}.tick span,.tick small{{display:block;color:var(--muted);font-size:11px}}.tick b{{display:block;font:700 13px ui-monospace,monospace;margin:3px 0;overflow-wrap:anywhere}}
.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:14px}}table{{width:100%;border-collapse:collapse;min-width:980px}}
th,td{{padding:11px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}th{{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);background:#f8f9fc}}
tr:last-child td{{border-bottom:0}}code{{font:12px ui-monospace,SFMono-Regular,Consolas,monospace}}.rule,.status{{display:inline-block;border-radius:99px;padding:3px 8px;font-size:10px;font-weight:800}}
.rule,.status.finding{{background:#fff0f2;color:#a72e45}}.status.match{{background:#e8f8f4;color:var(--green)}}
.digest{{display:grid;grid-template-columns:175px 1fr;gap:10px 18px}}.digest code{{overflow-wrap:anywhere;color:#354b69}}
footer{{color:var(--muted);font-size:12px;margin-top:24px;padding:0 6px}}
@media(max-width:850px){{header{{padding-bottom:88px}}.metrics{{grid-template-columns:repeat(2,1fr)}}.overview{{grid-template-columns:1fr}}.timeline{{grid-template-columns:repeat(3,1fr)}}}}
@media(max-width:480px){{main{{padding:20px 14px 50px}}header{{padding:38px 18px 82px}}.metrics{{gap:9px}}.metric{{padding:15px}}.metric strong{{font-size:28px}}section{{padding:18px}}.timeline{{grid-template-columns:repeat(2,1fr)}}.bar-row{{grid-template-columns:122px 1fr 22px}}.digest{{grid-template-columns:1fr;gap:3px}}}}
</style></head><body>
<header><div class="eyebrow">FeatureSeal / independently replayed ML data receipt</div>
<h1>Point-in-time features,<br>made auditable.</h1>
<p class="lead">Event time, availability time, freshness, and identity are replayed—not assumed.
Every mismatch receives one deterministic primary reason under a bounded contract.</p>
<div class="badges"><span class="badge">synthetic fixture</span>
<span class="badge">{summary["entities"]} entities</span><span class="badge">{summary["features"]} typed features</span>
<span class="badge">SQLite verifier passed</span></div></header>
<main><div class="metrics">{metric_cards}</div>
<div class="overview"><section><h2>Finding distribution</h2><p class="sub">Join-cell counts, not a production leakage rate.</p>{bars}</section>
<section><h2>Evidence boundary</h2><p class="sub">This receipt compares declared selections with point-in-time selections for one bounded synthetic snapshot.
It does not validate a feature store, labels, upstream event truth, model quality, or production behavior.</p>
<p><strong>{summary["observations"]}</strong> observations · <strong>{summary["features"]}</strong> feature contracts</p></section></div>
<section id="timeline"><h2>Availability timeline</h2><p class="sub">Each card shows event time → availability time; amber events arrived late.</p>
<div class="timeline">{timeline}</div></section>
<section id="findings"><h2>Bounded join findings</h2><p class="sub">Selected and expected events are explicit witnesses under the declared freshness windows.</p>
<div class="table-wrap"><table><thead><tr><th>ID</th><th>Reason</th><th>Observation</th><th>Feature</th><th>Selected</th><th>Expected</th><th>Explanation</th></tr></thead>
<tbody>{finding_rows}</tbody></table></div></section>
<section id="cells"><h2>Point-in-time join matrix</h2><p class="sub">All 28 declared cells, independently replayed.</p>
<div class="table-wrap"><table><thead><tr><th>Observation</th><th>At</th><th>Entity</th><th>Feature</th><th>Selected</th><th>Expected</th><th>Status</th></tr></thead>
<tbody>{cell_rows}</tbody></table></div></section>
<section id="receipt"><h2>Receipt integrity</h2><p class="sub">Canonical SHA-256 binds the normalized snapshot, derived cells, findings, and append-only ledger.</p>
<div class="digest"><strong>Snapshot SHA-256</strong><code>{_escape(receipt["snapshot_sha256"])}</code>
<strong>Ledger root</strong><code>{_escape(receipt["ledger_root_sha256"])}</code>
<strong>Receipt SHA-256</strong><code>{_escape(receipt["receipt_sha256"])}</code></div></section>
<footer>Generated deterministically by FeatureSeal v0.1.0 · no network, external database, or model required.</footer>
</main></body></html>
"""
