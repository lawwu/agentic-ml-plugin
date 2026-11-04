#!/usr/bin/env python3
"""
generate_report.py — Read JSON artifacts from a run directory and generate a
self-contained HTML report by embedding the data into viewer.html.

Usage:
    uv run "${CLAUDE_SKILL_DIR}/scripts/generate_report.py" <run-dir>
    uv run "${CLAUDE_SKILL_DIR}/scripts/generate_report.py" <run-dir> --out report.html
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

# Lifecycle order with gate numbers, used when run-summary.json has no gates.
# None = informational skill: shown, but never counted toward the overall decision.
SKILL_GATES = [
    ("select-approach", 0),
    ("review-target", 1),
    ("check-dataset-quality", 2),
    ("build-baseline", 3),
    ("plan-experiment", 4),
    ("feature-engineer", "4b"),
    ("check-data-pipeline", 5),
    ("train-model", 6),
    ("babysit-training", 6),
    ("check-failed-run", 6),
    ("check-eval", 7),
    ("explain-model", 8),
    ("check-deployment-readiness", 9),
    ("demonstrate-value", None),
    ("recommend-new-approaches", None),
]
SKILL_NAMES = [name for name, _ in SKILL_GATES]
GATE_NUMBERS = dict(SKILL_GATES)
INFORMATIONAL = {name for name, num in SKILL_GATES if num is None}

# run-summary.json uses "run-summary" as artifact key
ORCHESTRATOR_ARTIFACT = "run-summary"

# Evidence notebook files, read from the run directory only.
EVIDENCE_NOTEBOOK = "evidence.md"
EVIDENCE_VERIFY = "evidence-verify.txt"
EVIDENCE_CAP_BYTES = 2 * 1024 * 1024

DECISIONS = ("GO", "NO-GO", "CONDITIONAL")
GATE_STATUSES = ("PASS", "FAIL", "SKIPPED", "PENDING")


def _read_json(path: Path):
    """Return (data, error). error is a string when the file cannot be used."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, f"could not parse {path.name}: {e}"
    if not isinstance(data, dict):
        return None, f"{path.name} must contain a JSON object, got {type(data).__name__}"
    return data, None


def load_artifacts(run_dir: Path):
    """Load all known JSON artifacts. Returns (artifacts, artifact_files, load_errors)."""
    artifacts: dict = {}
    artifact_files: dict = {}
    load_errors: list = []

    for name in SKILL_NAMES + [ORCHESTRATOR_ARTIFACT]:
        path = run_dir / f"{name}.json"
        if not path.exists():
            continue
        artifact_files[name] = str(path)
        data, err = _read_json(path)
        if err:
            print(f"Warning: {err}", file=sys.stderr)
            load_errors.append({"artifact": name, "path": str(path), "error": err})
            if name != ORCHESTRATOR_ARTIFACT:
                # Keep a placeholder so the report shows the broken artifact.
                artifacts[name] = {
                    "skill_name": name,
                    "decision": "PENDING",
                    "summary": f"Artifact could not be loaded: {err}",
                    "findings": [],
                    "next_commands": [],
                    "_load_error": err,
                }
            continue
        if name != ORCHESTRATOR_ARTIFACT and not str(data.get("schema_version", "")).startswith("1."):
            print(f"Warning: {path.name} missing schema_version 1.x", file=sys.stderr)
        artifacts[name] = data

    return artifacts, artifact_files, load_errors


def _read_text_capped(path: Path, cap: int = EVIDENCE_CAP_BYTES):
    """Return (text, truncated) for a file, or (None, False) when it does not exist."""
    if not path.is_file():
        return None, False
    try:
        with open(path, "rb") as f:
            data = f.read(cap + 1)
    except OSError as e:
        print(f"Warning: could not read {path.name}: {e}", file=sys.stderr)
        return None, False
    truncated = len(data) > cap
    return data[:cap].decode("utf-8", errors="replace"), truncated


def load_evidence(run_dir: Path) -> dict:
    """Raw evidence notebook and verify output, embedded as plain strings."""
    nb_path = run_dir / EVIDENCE_NOTEBOOK
    verify_path = run_dir / EVIDENCE_VERIFY
    notebook, nb_truncated = _read_text_capped(nb_path)
    verify, verify_truncated = _read_text_capped(verify_path)
    return {
        "notebook": notebook,
        "notebook_path": str(nb_path) if notebook is not None else None,
        "notebook_truncated": nb_truncated,
        "verify": verify,
        "verify_path": str(verify_path) if verify is not None else None,
        "verify_truncated": verify_truncated,
    }


def _norm_decision(value) -> str:
    v = str(value or "").strip().upper()
    return v if v in DECISIONS else ""


def _norm_status(value) -> str:
    v = str(value or "").strip().upper()
    return v if v in GATE_STATUSES else ""


def _decision_to_gate_status(decision: str) -> str:
    # CONDITIONAL is a pass with caveats; the viewer shows it as "PASS · conditional".
    return {"GO": "PASS", "CONDITIONAL": "PASS", "NO-GO": "FAIL"}.get(decision, "PENDING")


def _normalize_gate(gate, index: int, run_dir: Path, artifacts: dict):
    if not isinstance(gate, dict):
        return None
    name = str(gate.get("gate_name") or "")
    art = artifacts.get(name, {})
    decision = _norm_decision(gate.get("decision")) or _norm_decision(art.get("decision"))
    status = _norm_status(gate.get("status"))
    if not status:
        status = _decision_to_gate_status(decision)
    if not decision and status == "FAIL":
        decision = "NO-GO"
    artifact_path = gate.get("artifact_path")
    if not artifact_path and name:
        candidate = run_dir / f"{name}.json"
        artifact_path = str(candidate) if candidate.exists() else ""
    gate_number = gate.get("gate_number")
    valid_label = isinstance(gate_number, str) and 0 < len(gate_number) <= 4
    if not (isinstance(gate_number, int) and not isinstance(gate_number, bool)) and not valid_label:
        gate_number = GATE_NUMBERS.get(name, index)
    return {
        "gate_number": gate_number,
        "gate_name": name,
        "informational": bool(gate.get("informational")) or name in INFORMATIONAL,
        "status": status,
        "decision": decision,
        "artifact_path": artifact_path or "",
        "timestamp": str(gate.get("timestamp") or art.get("timestamp") or ""),
    }


def derive_overall(artifacts: dict, run_dir: Path) -> dict:
    """Compute an overall run summary from loaded artifacts."""
    summary = artifacts.get(ORCHESTRATOR_ARTIFACT, {})

    first_run_id = next(
        (a.get("run_id") for a in artifacts.values() if isinstance(a, dict) and a.get("run_id")),
        None,
    )
    run_id = summary.get("run_id") or first_run_id or "unknown"
    timestamp = summary.get("timestamp") or datetime.now(timezone.utc).isoformat()
    decision = _norm_decision(summary.get("decision")) or "PENDING"
    confidence = summary.get("confidence", "low")
    objective = summary.get("objective", "")

    raw_gates = summary.get("gates")
    gates = []
    if isinstance(raw_gates, list) and raw_gates:
        for i, g in enumerate(raw_gates, start=1):
            norm = _normalize_gate(g, i, run_dir, artifacts)
            if norm:
                gates.append(norm)
    else:
        # Fallback: derive gates from individual artifacts in lifecycle order.
        for name, number in SKILL_GATES:
            if name in artifacts:
                art = artifacts[name]
                dec = _norm_decision(art.get("decision"))
                gates.append(
                    {
                        "gate_number": number,
                        "gate_name": name,
                        "informational": name in INFORMATIONAL,
                        "status": _decision_to_gate_status(dec),
                        "decision": dec,
                        "artifact_path": str(run_dir / f"{name}.json"),
                        "timestamp": str(art.get("timestamp") or ""),
                    }
                )

    # Overall decision fallback: derive from gates.
    if decision == "PENDING" and gates:
        active = [g for g in gates if g["status"] != "SKIPPED" and not g.get("informational")]
        if any(g["status"] == "FAIL" or g["decision"] == "NO-GO" for g in active):
            decision = "NO-GO"
        elif active and all(g["status"] == "PASS" for g in active):
            decision = "CONDITIONAL" if any(g["decision"] == "CONDITIONAL" for g in active) else "GO"

    def _str_list(v):
        return [str(x) for x in v] if isinstance(v, list) else []

    def _opt_str(v):
        return str(v) if isinstance(v, (str, int, float)) and str(v) else ""

    mlts = summary.get("ml_test_score")
    evidence = summary.get("evidence")

    return {
        "run_id": str(run_id),
        "timestamp": str(timestamp),
        "decision": decision,
        "confidence": str(confidence or ""),
        "objective": str(objective or ""),
        "gates": gates,
        "top_blockers": _str_list(summary.get("top_blockers")),
        "top_risks": _str_list(summary.get("top_risks")),
        "level": _opt_str(summary.get("level")),
        "autonomy": _opt_str(summary.get("autonomy")),
        "approach": _opt_str(summary.get("approach")),
        "ml_test_score": mlts if isinstance(mlts, dict) else None,
        "evidence": evidence if isinstance(evidence, dict) else None,
    }


def _script_safe_json(obj) -> str:
    """Serialize for embedding inside <script>: no '<', '>', '&' or line separators survive raw."""
    text = json.dumps(obj, indent=2, default=str)
    return (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def render_html(template_path: Path, embedded: dict) -> str:
    """Embed artifact data into the HTML template."""
    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    placeholder = "const EMBEDDED_DATA = null;"
    if placeholder not in template:
        raise ValueError("Placeholder 'const EMBEDDED_DATA = null;' not found in template")
    # str.replace avoids regex backreference issues with backslashes in the payload.
    return template.replace(placeholder, f"const EMBEDDED_DATA = {_script_safe_json(embedded)};", 1)


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

    template_path = Path(__file__).resolve().parent / "viewer.html"
    if not template_path.exists():
        print(f"Error: viewer.html not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    artifacts, artifact_files, load_errors = load_artifacts(run_dir)
    if not artifacts:
        print(f"Warning: no recognized JSON artifacts found in {run_dir}", file=sys.stderr)

    overall = derive_overall(artifacts, run_dir)
    embedded = {
        "overall": overall,
        "artifacts": artifacts,
        "artifact_files": artifact_files,
        "load_errors": load_errors,
        "evidence": load_evidence(run_dir),
        "run_dir": str(run_dir),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    html = render_html(template_path, embedded)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report written to: {out_path}")
    print(f"  Run ID:   {overall['run_id']}")
    print(f"  Decision: {overall['decision']}")
    print(f"  Artifacts loaded: {list(artifacts.keys())}")
    if load_errors:
        print(f"  Load errors: {len(load_errors)} (see report)")


if __name__ == "__main__":
    main()
