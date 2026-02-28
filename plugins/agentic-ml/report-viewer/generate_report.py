#!/usr/bin/env python3
"""
generate_report.py — Read JSON artifacts from a run directory and generate a
self-contained HTML report by embedding the data into viewer.html.

Usage:
    uv run plugins/agentic-ml/report-viewer/generate_report.py <run-dir>
    uv run plugins/agentic-ml/report-viewer/generate_report.py <run-dir> --out report.html
"""
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_NAMES = [
    "review-target",
    "plan-experiment",
    "check-dataset-quality",
    "check-data-pipeline",
    "feature-engineer",
    "babysit-training",
    "check-failed-run",
    "check-eval",
    "explain-model",
]

# run-summary.json uses "run-summary" as artifact key
ORCHESTRATOR_ARTIFACT = "run-summary"


def load_artifacts(run_dir: Path) -> dict:
    """Load all known JSON artifacts from the run directory."""
    artifacts = {}

    for name in SKILL_NAMES:
        path = run_dir / f"{name}.json"
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                # Basic schema_version check
                if data.get("schema_version") != "1.0":
                    print(
                        f"Warning: {path.name} missing schema_version=1.0", file=sys.stderr
                    )
                artifacts[name] = data
            except json.JSONDecodeError as e:
                print(f"Warning: could not parse {path.name}: {e}", file=sys.stderr)

    # Load orchestrate-e2e summary
    summary_path = run_dir / "run-summary.json"
    if summary_path.exists():
        try:
            with open(summary_path) as f:
                artifacts[ORCHESTRATOR_ARTIFACT] = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Warning: could not parse run-summary.json: {e}", file=sys.stderr)

    return artifacts


def derive_overall(artifacts: dict) -> dict:
    """Compute an overall run summary from loaded artifacts."""
    summary = artifacts.get(ORCHESTRATOR_ARTIFACT, {})

    run_id = summary.get("run_id", "unknown")
    timestamp = summary.get("timestamp", datetime.now(timezone.utc).isoformat())
    decision = summary.get("decision", "PENDING")
    confidence = summary.get("confidence", "low")
    objective = summary.get("objective", "")

    # Collect gate statuses
    gates = summary.get("gates", [])

    # Fallback: derive gates from individual artifacts
    if not gates:
        for i, name in enumerate(SKILL_NAMES, start=1):
            if name in artifacts:
                art = artifacts[name]
                gates.append(
                    {
                        "gate_number": i,
                        "gate_name": name,
                        "status": _decision_to_gate_status(art.get("decision", "PENDING")),
                        "artifact_path": str(run_id),
                        "timestamp": art.get("timestamp", ""),
                        "decision": art.get("decision", "PENDING"),
                    }
                )

    # Overall decision fallback: derive from gates
    if decision == "PENDING" and gates:
        decisions = [g.get("decision", "PENDING") for g in gates]
        if any(d == "NO-GO" for d in decisions):
            decision = "NO-GO"
        elif all(d in ("GO", "CONDITIONAL") for d in decisions):
            decision = "GO" if all(d == "GO" for d in decisions) else "CONDITIONAL"

    return {
        "run_id": run_id,
        "timestamp": timestamp,
        "decision": decision,
        "confidence": confidence,
        "objective": objective,
        "gates": gates,
        "top_blockers": summary.get("top_blockers", []),
        "top_risks": summary.get("top_risks", []),
    }


def _decision_to_gate_status(decision: str) -> str:
    mapping = {"GO": "PASS", "NO-GO": "FAIL", "CONDITIONAL": "PASS", "PENDING": "PENDING"}
    return mapping.get(decision, "SKIPPED")


def render_html(template_path: Path, artifacts: dict, overall: dict) -> str:
    """Embed artifact data into the HTML template."""
    with open(template_path) as f:
        template = f.read()

    embedded = {
        "overall": overall,
        "artifacts": artifacts,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    js_payload = json.dumps(embedded, indent=2, default=str)

    # Replace the placeholder in the template using str.replace to avoid
    # regex backreference issues with backslashes in the JSON payload.
    placeholder = "const EMBEDDED_DATA = null;"
    replacement = f"const EMBEDDED_DATA = {js_payload};"
    if placeholder not in template:
        raise ValueError("Placeholder 'const EMBEDDED_DATA = null;' not found in template")
    result = template.replace(placeholder, replacement, 1)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML report from run artifacts")
    parser.add_argument("run_dir", help="Path to the run directory containing JSON artifacts")
    parser.add_argument(
        "--out",
        default=None,
        help="Output HTML path (default: <run-dir>/report.html)",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"Error: run directory does not exist: {run_dir}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out).resolve() if args.out else run_dir / "report.html"

    template_path = Path(__file__).parent / "viewer.html"
    if not template_path.exists():
        print(f"Error: viewer.html not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    artifacts = load_artifacts(run_dir)
    if not artifacts:
        print(f"Warning: no recognized JSON artifacts found in {run_dir}", file=sys.stderr)

    overall = derive_overall(artifacts)
    html = render_html(template_path, artifacts, overall)

    with open(out_path, "w") as f:
        f.write(html)

    print(f"Report written to: {out_path}")
    print(f"  Run ID:   {overall['run_id']}")
    print(f"  Decision: {overall['decision']}")
    print(f"  Artifacts loaded: {list(artifacts.keys())}")


if __name__ == "__main__":
    main()
