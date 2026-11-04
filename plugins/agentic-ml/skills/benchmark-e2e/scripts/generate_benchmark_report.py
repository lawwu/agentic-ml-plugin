#!/usr/bin/env python3
"""
generate_benchmark_report.py — Read benchmark-report.json from a benchmark run
directory and produce a self-contained HTML scorecard.

Usage:
    uv run "${CLAUDE_SKILL_DIR}/scripts/generate_benchmark_report.py" <run-dir>
    uv run "${CLAUDE_SKILL_DIR}/scripts/generate_benchmark_report.py" <run-dir> --out benchmark-report.html
"""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────
# Every value read from benchmark-report.json goes through _e() before it is
# placed in the HTML.

def _e(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    return html.escape(str(value), quote=True)


def _num(value) -> float | None:
    """Coerce to a finite float, or None."""
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


BADGE_CLASS = {
    "GO": "go", "NO-GO": "nogo", "CONDITIONAL": "cond",
    "PASS": "go", "FAIL": "nogo", "SKIPPED": "skipped", "PENDING": "skipped",
}


def _badge(value) -> str:
    label = str(value)
    cls = BADGE_CLASS.get(label.upper(), "skipped")
    return f'<span class="badge badge-{cls}">{_e(label)}</span>'


def _score_bar(score) -> str:
    n = _num(score)
    if n is None:
        return '<span class="muted">—</span>' if score in (None, "", "unknown") else _e(score)
    color = "#16a34a" if n >= 70 else "#d97706" if n >= 45 else "#dc2626"
    width = max(0.0, min(100.0, n))
    shown = int(n) if n == int(n) else round(n, 1)
    return (
        f'<div class="score-bar-wrap">'
        f'<div class="score-bar" style="width:{width:.0f}%;background:{color}"></div>'
        f'<span class="score-num">{_e(shown)}</span>'
        f'</div>'
    )


def _cell(value) -> str:
    if value is None or value == "unknown":
        return '<td class="muted">unknown</td>'
    return f"<td>{_e(value)}</td>"


# Lifecycle stages in gate order. stage_coverage[mode] may be keyed by the
# skill name (preferred), the label, or the numbered label ("1. Target readiness").
STAGES = [
    ("review-target", "Target readiness"),
    ("check-dataset-quality", "Dataset quality"),
    ("build-baseline", "Non-ML baseline"),
    ("plan-experiment", "Experiment plan"),
    ("check-data-pipeline", "Data pipeline"),
    ("train-model", "Training stability"),
    ("check-eval", "Evaluation quality"),
    ("explain-model", "Interpretability/bias"),
    ("promotion-decision", "Promotion decision"),
]

# Skills expected in plugin mode when no explicit skill_audit is provided.
# babysit-training / check-failed-run are invoked by train-model as needed.
PLUGIN_EXPECTED_SKILLS = [
    "review-target", "check-dataset-quality", "build-baseline", "plan-experiment",
    "check-data-pipeline", "train-model", "check-eval", "explain-model",
]


def _stage_cell(coverage: dict, index: int, skill: str, label: str):
    for key in (skill, label, f"{index}. {label}"):
        if key in coverage:
            return coverage[key]
    return None

# ── HTML template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Benchmark Report — {run_id}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --go: #16a34a; --go-bg: #dcfce7; --go-border: #86efac;
    --nogo: #dc2626; --nogo-bg: #fee2e2; --nogo-border: #fca5a5;
    --cond: #d97706; --cond-bg: #fef3c7; --cond-border: #fcd34d;
    --skipped: #9ca3af;
    --blocker: #dc2626; --high: #ea580c; --medium: #d97706; --low: #6b7280;
    --bg: #f9fafb; --card: #ffffff; --border: #e5e7eb; --text: #111827;
    --muted: #6b7280; --code-bg: #f3f4f6;
  }}
  body {{ font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5; }}
  header {{ background: #1e293b; color: white; padding: 16px 24px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}
  header h1 {{ font-size: 18px; font-weight: 600; flex: 1; min-width: 200px; }}
  .run-meta {{ font-size: 12px; color: #94a3b8; }}
  .badge {{ display: inline-flex; align-items: center; padding: 3px 10px; border-radius: 9999px; font-weight: 700; font-size: 12px; border: 2px solid; white-space: nowrap; }}
  .badge-go    {{ color: var(--go);   background: var(--go-bg);   border-color: var(--go-border); }}
  .badge-nogo  {{ color: var(--nogo); background: var(--nogo-bg); border-color: var(--nogo-border); }}
  .badge-cond  {{ color: var(--cond); background: var(--cond-bg); border-color: var(--cond-border); }}
  .badge-skipped {{ color: var(--skipped); background: #f3f4f6; border-color: #d1d5db; }}
  main {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px; display: flex; flex-direction: column; gap: 24px; }}
  section {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }}
  section h2 {{ font-size: 15px; font-weight: 600; margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f1f5f9; padding: 8px 12px; text-align: left; font-weight: 600; border-bottom: 2px solid var(--border); white-space: nowrap; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  .muted {{ color: var(--muted); }}
  .score-bar-wrap {{ display: flex; align-items: center; gap: 8px; min-width: 100px; }}
  .score-bar {{ height: 8px; border-radius: 4px; min-width: 2px; }}
  .score-num {{ font-weight: 700; font-size: 13px; white-space: nowrap; }}
  .rank-1 {{ background: #fef9c3; }}
  .rank-2 {{ background: #f0fdf4; }}
  .rank-3 {{ background: #fff7ed; }}
  .finding {{ border-left: 4px solid; padding: 10px 14px; border-radius: 0 6px 6px 0; margin-bottom: 10px; }}
  .finding-blocker {{ border-color: var(--blocker); background: #fee2e2; }}
  .finding-high    {{ border-color: var(--high);    background: #fff7ed; }}
  .finding-medium  {{ border-color: var(--medium);  background: var(--cond-bg); }}
  .finding-low     {{ border-color: var(--low);     background: #f9fafb; }}
  .finding-title {{ font-weight: 600; font-size: 13px; }}
  .finding-body  {{ font-size: 12px; color: #374151; margin-top: 4px; }}
  .finding-fix   {{ font-size: 12px; color: #16a34a; margin-top: 4px; }}
  .rec-card {{ border: 1px solid var(--border); border-radius: 6px; padding: 14px 16px; margin-bottom: 10px; }}
  .rec-card h3 {{ font-size: 13px; font-weight: 700; margin-bottom: 6px; }}
  .rec-card p  {{ font-size: 13px; color: #374151; }}
  .check {{ color: #16a34a; font-weight: 700; }}
  .cross {{ color: #dc2626; font-weight: 700; }}
  .stage-cell {{ font-size: 12px; }}
  code {{ background: var(--code-bg); padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
  .generated {{ font-size: 11px; color: var(--muted); text-align: right; margin-top: 8px; }}
</style>
</head>
<body>
<header>
  <h1>⚡ E2E Benchmark Report</h1>
  <div>
    <div class="run-meta">Run ID: {run_id}</div>
    <div class="run-meta">Scenario: <strong>{scenario}</strong> ({scenario_detection}) &nbsp;·&nbsp; Primary metric: <strong>{primary_metric}</strong></div>
    <div class="run-meta">Modes: {modes_str} &nbsp;·&nbsp; {timestamp}</div>
  </div>
  {overall_badge}
</header>
<main>

<!-- RESULTS SCORECARD -->
<section>
  <h2>Results Scorecard</h2>
  <table>
    <thead>
      <tr>
        <th>Rank</th><th>Mode</th><th>Scenario</th>
        <th>Quality (35%)</th><th>Reliability (25%)</th>
        <th>Efficiency (20%)</th><th>Ops Readiness (20%)</th>
        <th>LOC Run</th><th>Tokens In</th><th>Tokens Out</th><th>Tokens Total</th>
        <th>Total</th>
      </tr>
    </thead>
    <tbody>
      {results_rows}
    </tbody>
  </table>
</section>

<!-- STAGE COVERAGE -->
<section>
  <h2>Stage Coverage</h2>
  <table>
    <thead>
      <tr><th>Stage</th>{stage_mode_headers}</tr>
    </thead>
    <tbody>
      {stage_rows}
    </tbody>
  </table>
</section>

<!-- SKILL AUDIT -->
<section>
  <h2>Skill Usage Audit</h2>
  <table>
    <thead>
      <tr><th>Mode</th><th>Expected Skills</th><th>Actual Skills</th><th>Missing</th><th>Extra</th></tr>
    </thead>
    <tbody>
      {skill_audit_rows}
    </tbody>
  </table>
</section>

<!-- FINDINGS -->
{findings_section}

<!-- RECOMMENDATION -->
<section>
  <h2>Recommendation</h2>
  {recommendation_html}
</section>

<p class="generated">Generated {generated_at} by generate_benchmark_report.py</p>
</main>
</body>
</html>
"""


# ── rendering ──────────────────────────────────────────────────────────────────

def render_results_rows(results: list) -> str:
    rows_in = [_dict(r) for r in results]
    sorted_results = sorted(
        rows_in,
        key=lambda r: _num(r.get("total_score")) if _num(r.get("total_score")) is not None else -math.inf,
        reverse=True,
    )
    rows = []
    for rank, r in enumerate(sorted_results, 1):
        cls = f"rank-{rank}" if rank <= 3 else ""
        rows.append(
            f'<tr class="{cls}">'
            f"<td><strong>#{rank}</strong></td>"
            f"<td><strong>{_e(r.get('mode', '?'))}</strong></td>"
            f"<td>{_e(r.get('scenario', '?'))}</td>"
            f"<td>{_score_bar(r.get('quality_score'))}</td>"
            f"<td>{_score_bar(r.get('reliability_score'))}</td>"
            f"<td>{_score_bar(r.get('efficiency_score'))}</td>"
            f"<td>{_score_bar(r.get('ops_readiness_score'))}</td>"
            + _cell(r.get("loc_run"))
            + _cell(r.get("tokens_in"))
            + _cell(r.get("tokens_out"))
            + _cell(r.get("tokens_total"))
            + f"<td><strong>{_score_bar(r.get('total_score'))}</strong></td>"
            f"</tr>"
        )
    return "\n      ".join(rows)


def render_stage_rows(data: dict) -> tuple[str, str]:
    """Return (mode_headers, stage_rows)."""
    modes = []
    for r in _list(data.get("results")):
        mode = str(_dict(r).get("mode", "?"))
        if mode not in modes:
            modes.append(mode)
    headers = "".join(f"<th>{_e(m)}</th>" for m in modes)

    stage_coverage = _dict(data.get("stage_coverage"))

    rows = []
    for i, (skill, label) in enumerate(STAGES, 1):
        row = f"<tr><td><strong>{i}. {_e(label)}</strong></td>"
        for mode in modes:
            cell = _stage_cell(_dict(stage_coverage.get(mode)), i, skill, label)
            if cell in (None, "", "—"):
                row += '<td class="stage-cell muted">—</td>'
            else:
                row += f'<td class="stage-cell">{_badge(cell)}</td>'
        row += "</tr>"
        rows.append(row)

    return headers, "\n      ".join(rows)


def _join(items, empty: str) -> str:
    items = [_e(x) for x in _list(items)]
    return ", ".join(items) if items else empty


NONE_HTML = '<span class="muted">none</span>'


def render_skill_audit(data: dict) -> str:
    audit = _list(data.get("skill_audit"))
    if not audit:
        # Derive minimal from results
        rows = []
        seen = set()
        for r in _list(data.get("results")):
            mode = str(_dict(r).get("mode", "?"))
            if mode in seen:
                continue
            seen.add(mode)
            if mode == "plugin":
                rows.append(
                    f"<tr><td>{_e(mode)}</td>"
                    f"<td>{_e(', '.join(PLUGIN_EXPECTED_SKILLS))}</td>"
                    f"<td><em>(as invoked)</em></td>"
                    f"<td>—</td><td>—</td></tr>"
                )
            else:
                rows.append(
                    f"<tr><td>{_e(mode)}</td>"
                    f"<td class='muted'>none (0 expected)</td>"
                    f"<td class='muted'>none</td>"
                    f"<td>—</td><td>—</td></tr>"
                )
        return "\n      ".join(rows)

    rows = []
    for raw in audit:
        entry = _dict(raw)
        rows.append(
            f"<tr>"
            f"<td>{_e(entry.get('mode', '?'))}</td>"
            f"<td>{_join(entry.get('expected'), NONE_HTML)}</td>"
            f"<td>{_join(entry.get('actual'), NONE_HTML)}</td>"
            f"<td>{_join(entry.get('missing'), '—')}</td>"
            f"<td>{_join(entry.get('extra'), '—')}</td>"
            "</tr>"
        )
    return "\n      ".join(rows)


SEVERITIES = ("blocker", "high", "medium", "low")


def render_findings(findings: list) -> str:
    findings = [_dict(f) for f in _list(findings)]
    if not findings:
        return ""
    items = []
    for f in findings:
        sev = str(f.get("severity", "low")).lower()
        sev = sev if sev in SEVERITIES else "low"
        fix = f.get("fix", "")
        fix_html = f'<div class="finding-fix">Fix: {_e(fix)}</div>' if fix else ""
        items.append(
            f'<div class="finding finding-{sev}">'
            f'<div class="finding-title">[{sev.upper()}] {_e(f.get("title", ""))}</div>'
            f'<div class="finding-body">{_e(f.get("description", ""))}</div>'
            f"{fix_html}"
            f"</div>"
        )
    return (
        '<section><h2>Findings</h2>'
        + "\n".join(items)
        + "</section>"
    )


def render_recommendation(rec: dict) -> str:
    rec = _dict(rec)
    default = rec.get("default_mode", "—")
    default_why = rec.get("default_mode_rationale", "")
    fallback = rec.get("fallback_mode", "—")
    fallback_why = rec.get("fallback_mode_rationale", "")

    return (
        f'<div class="rec-card">'
        f'<h3>✅ Default mode: <code>{_e(default)}</code></h3>'
        f"<p>{_e(default_why)}</p>"
        f"</div>"
        f'<div class="rec-card">'
        f'<h3>↩ Fallback mode: <code>{_e(fallback)}</code></h3>'
        f"<p>{_e(fallback_why)}</p>"
        f"</div>"
    )


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML benchmark report from benchmark-report.json")
    parser.add_argument("run_dir", help="Path to the benchmark run directory containing benchmark-report.json")
    parser.add_argument("--out", default=None, help="Output HTML path (default: <run-dir>/benchmark-report.html)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"Error: run directory does not exist: {run_dir}", file=sys.stderr)
        sys.exit(1)

    report_path = run_dir / "benchmark-report.json"
    if not report_path.exists():
        print(f"Error: benchmark-report.json not found in {run_dir}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out).resolve() if args.out else run_dir / "benchmark-report.html"

    try:
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error: could not parse {report_path}: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print(f"Error: {report_path} must contain a JSON object", file=sys.stderr)
        sys.exit(1)

    run_id          = data.get("run_id", "unknown")
    scenario        = data.get("selected_scenario", "unknown")
    scenario_det    = data.get("scenario_detection", "auto")
    primary_metric  = data.get("primary_metric", "unknown")
    modes           = [str(m) for m in _list(data.get("modes"))]
    timestamp       = data.get("timestamp", "")
    results         = _list(data.get("results"))
    findings        = _list(data.get("findings"))
    recommendation  = _dict(data.get("recommendation"))
    decision        = str(data.get("decision", "GO"))

    stage_headers, stage_rows = render_stage_rows(data)

    page = HTML_TEMPLATE.format(
        run_id=_e(run_id),
        scenario=_e(scenario),
        scenario_detection=_e(scenario_det),
        primary_metric=_e(primary_metric),
        modes_str=_e(", ".join(modes)),
        timestamp=_e(timestamp),
        overall_badge=_badge(decision),
        results_rows=render_results_rows(results),
        stage_mode_headers=stage_headers,
        stage_rows=stage_rows,
        skill_audit_rows=render_skill_audit(data),
        findings_section=render_findings(findings),
        recommendation_html=render_recommendation(recommendation),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"Benchmark report written to: {out_path}")
    print(f"  Run ID:   {run_id}")
    print(f"  Scenario: {scenario}")
    print(f"  Modes:    {', '.join(modes)}")
    print(f"  Decision: {decision}")


if __name__ == "__main__":
    main()
