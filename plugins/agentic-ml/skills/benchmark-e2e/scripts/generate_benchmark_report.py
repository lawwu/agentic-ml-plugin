#!/usr/bin/env python3
"""
generate_benchmark_report.py — Read benchmark-report.json from a benchmark run
directory and produce a self-contained HTML scorecard.

Usage:
    uv run plugins/agentic-ml/skills/benchmark-e2e/scripts/generate_benchmark_report.py <run-dir>
    uv run plugins/agentic-ml/skills/benchmark-e2e/scripts/generate_benchmark_report.py <run-dir> --out benchmark-report.html
"""
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────

def _badge(value: str) -> str:
    cls = {
        "GO": "go", "NO-GO": "nogo", "CONDITIONAL": "cond",
        "PASS": "go", "FAIL": "nogo", "SKIPPED": "skipped",
    }.get(str(value).upper(), "skipped")
    label = "NO-GO" if str(value).upper() == "NO-GO" else value
    return f'<span class="badge badge-{cls}">{label}</span>'


def _score_bar(score: int | float | str) -> str:
    if score == "unknown" or score is None:
        return '<span class="muted">—</span>'
    score = int(score)
    color = "#16a34a" if score >= 70 else "#d97706" if score >= 45 else "#dc2626"
    return (
        f'<div class="score-bar-wrap">'
        f'<div class="score-bar" style="width:{score}%;background:{color}"></div>'
        f'<span class="score-num">{score}</span>'
        f'</div>'
    )


def _cell(value) -> str:
    if value is None or value == "unknown":
        return '<td class="muted">unknown</td>'
    return f"<td>{value}</td>"


STAGE_LABELS = [
    "1. Target readiness",
    "2. Experiment plan",
    "3. Dataset quality",
    "4. Data pipeline",
    "5. Training stability",
    "6. Evaluation quality",
    "7. Interpretability/bias",
    "8. Promotion decision",
]

PITFALL_KEYS = [
    ("target_echo", "Target echo"),
    ("near_perfect_leak", "Near-perfect leak"),
    ("wrong_metric", "Wrong metric (AUC vs AUPRC)"),
    ("selection_bias", "Selection bias"),
    ("geographic_proxy", "Geographic proxy bias"),
    ("split_boundary", "Split boundary tie"),
    ("feedback_loop", "Feedback loop"),
]

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
    sorted_results = sorted(results, key=lambda r: -(r.get("total_score") or 0))
    rows = []
    for rank, r in enumerate(sorted_results, 1):
        cls = f"rank-{rank}" if rank <= 3 else ""
        rows.append(
            f'<tr class="{cls}">'
            f"<td><strong>#{rank}</strong></td>"
            f"<td><strong>{r.get('mode','?')}</strong></td>"
            f"<td>{r.get('scenario','?')}</td>"
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
    results = data.get("results", [])
    modes = [r.get("mode", "?") for r in results]
    headers = "".join(f"<th>{m}</th>" for m in modes)

    # Build stage coverage from results if present, else placeholder
    stage_coverage = data.get("stage_coverage", {})

    rows = []
    for label in STAGE_LABELS:
        row = f'<tr><td><strong>{label}</strong></td>'
        for mode in modes:
            cell = stage_coverage.get(mode, {}).get(label, "—")
            if cell == "—":
                row += f'<td class="stage-cell muted">—</td>'
            else:
                row += f'<td class="stage-cell">{_badge(cell)}</td>'
        row += "</tr>"
        rows.append(row)

    return headers, "\n      ".join(rows)


def render_skill_audit(data: dict) -> str:
    audit = data.get("skill_audit", [])
    if not audit:
        # Derive minimal from results
        rows = []
        for r in data.get("results", []):
            mode = r.get("mode", "?")
            if mode == "plugin":
                rows.append(
                    f"<tr><td>{mode}</td>"
                    f"<td>review-target, plan-experiment, check-dataset-quality,<br>check-data-pipeline, babysit-training, check-eval, explain-model</td>"
                    f"<td><em>(as invoked)</em></td>"
                    f"<td>—</td><td>—</td></tr>"
                )
            else:
                rows.append(
                    f"<tr><td>{mode}</td>"
                    f"<td class='muted'>none (0 expected)</td>"
                    f"<td class='muted'>none</td>"
                    f"<td>—</td><td>—</td></tr>"
                )
        return "\n      ".join(rows)

    rows = []
    for entry in audit:
        rows.append(
            f"<tr>"
            f"<td>{entry.get('mode','?')}</td>"
            + ("<td>" + (", ".join(entry.get("expected", [])) or '<span class="muted">none</span>') + "</td>")
            + ("<td>" + (", ".join(entry.get("actual", [])) or '<span class="muted">none</span>') + "</td>")
            + ("<td>" + (", ".join(entry.get("missing", [])) or "—") + "</td>")
            + ("<td>" + (", ".join(entry.get("extra", [])) or "—") + "</td>")
            + "</tr>"
        )
    return "\n      ".join(rows)


def render_findings(findings: list) -> str:
    if not findings:
        return ""
    items = []
    for f in findings:
        sev = f.get("severity", "low")
        fix = f.get("fix", "")
        fix_html = f'<div class="finding-fix">Fix: {fix}</div>' if fix else ""
        items.append(
            f'<div class="finding finding-{sev}">'
            f'<div class="finding-title">[{sev.upper()}] {f.get("title","")}</div>'
            f'<div class="finding-body">{f.get("description","")}</div>'
            f"{fix_html}"
            f"</div>"
        )
    return (
        '<section><h2>Findings</h2>'
        + "\n".join(items)
        + "</section>"
    )


def render_recommendation(rec: dict) -> str:
    default = rec.get("default_mode", "—")
    default_why = rec.get("default_mode_rationale", "")
    fallback = rec.get("fallback_mode", "—")
    fallback_why = rec.get("fallback_mode_rationale", "")

    return (
        f'<div class="rec-card">'
        f'<h3>✅ Default mode: <code>{default}</code></h3>'
        f"<p>{default_why}</p>"
        f"</div>"
        f'<div class="rec-card">'
        f'<h3>↩ Fallback mode: <code>{fallback}</code></h3>'
        f"<p>{fallback_why}</p>"
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

    with open(report_path) as f:
        data = json.load(f)

    run_id          = data.get("run_id", "unknown")
    scenario        = data.get("selected_scenario", "unknown")
    scenario_det    = data.get("scenario_detection", "auto")
    primary_metric  = data.get("primary_metric", "unknown")
    modes           = data.get("modes", [])
    timestamp       = data.get("timestamp", "")
    results         = data.get("results", [])
    findings        = data.get("findings", [])
    recommendation  = data.get("recommendation", {})
    decision        = data.get("decision", "GO")

    results_rows        = render_results_rows(results)
    stage_headers, stage_rows = render_stage_rows(data)
    skill_audit_rows    = render_skill_audit(data)
    findings_section    = render_findings(findings)
    recommendation_html = render_recommendation(recommendation)
    decision_cls        = decision.lower().replace("-", "")
    overall_badge       = f'<span class="badge badge-{decision_cls}">{decision}</span>'

    html = HTML_TEMPLATE.format(
        run_id=run_id,
        scenario=scenario,
        scenario_detection=scenario_det,
        primary_metric=primary_metric,
        modes_str=", ".join(modes),
        timestamp=timestamp,
        overall_badge=overall_badge,
        results_rows=results_rows,
        stage_mode_headers=stage_headers,
        stage_rows=stage_rows,
        skill_audit_rows=skill_audit_rows,
        findings_section=findings_section,
        recommendation_html=recommendation_html,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    with open(out_path, "w") as f:
        f.write(html)

    print(f"Benchmark report written to: {out_path}")
    print(f"  Run ID:   {run_id}")
    print(f"  Scenario: {scenario}")
    print(f"  Modes:    {', '.join(modes)}")
    print(f"  Decision: {decision}")


if __name__ == "__main__":
    main()
