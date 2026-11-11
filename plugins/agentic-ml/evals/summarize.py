#!/usr/bin/env python3
"""
summarize.py — turn a `claude plugin eval --json` result into a per-skill table, and optionally add one
line to a history file so scores can be followed across plugin versions and models.

Usage:
    uv run plugins/agentic-ml/evals/summarize.py <result.json> [--history evals/history.jsonl] [--json]

A case belongs to the skill named by its first tag. Tag a case `planted` when the right answer is to stop
or to flag something, and `clean` when the right answer is to proceed. Per skill the table shows:

    with      mean case score with the plugin (0 to 1)
    without   mean case score without it
    delta     with minus without
    planted   planted cases passed / planted cases   (a miss here is a defect that got through)
    clean     clean cases passed / clean cases       (a miss here is a false alarm)
    cost      dollars spent on the skill's runs, both arms

Reads the result file only. Writes nothing unless --history is given.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def frontmatter_tags(case_dir: Path) -> list[str]:
    """Tags from a case's prompt.md or case.yaml (`tags: [a, b]`), without a YAML dependency."""
    for name in ("case.yaml", "prompt.md"):
        f = case_dir / name
        if not f.is_file():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("tags:"):
                inner = line.split(":", 1)[1].strip().strip("[]")
                return [t.strip().strip("'\"") for t in inner.split(",") if t.strip()]
    return []


def git_sha(path: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def summarize(result: dict) -> dict:
    root = Path(result["suite"]["root"])
    skills: dict[str, dict] = {}
    cases = []
    for c in result["cases"]:
        tags = frontmatter_tags(root / c["dir"])
        skill = tags[0] if tags else "untagged"
        agg = c.get("aggregates") or {}
        runs = [r for arm in (c.get("arms") or {}).values() for r in arm]
        row = {"case": c["name"], "skill": skill, "tags": tags, "with": agg.get("score"), "without": agg.get("scoreWithout"),
               "delta": agg.get("delta"), "passed": (agg.get("passRate") or 0) >= 1,
               "runs": len((c.get("arms") or {}).get("with") or []),
               "errors": sum(1 for r in runs if r.get("error")),
               "cost": round(sum((r.get("costUsd") or 0) + (r.get("judgeCostUsd") or 0) for r in runs), 4)}
        cases.append(row)
        s = skills.setdefault(skill, {"cases": 0, "with": [], "without": [], "planted": [0, 0], "clean": [0, 0], "cost": 0.0, "errors": 0})
        s["cases"] += 1
        s["cost"] += row["cost"]
        s["errors"] += row["errors"]
        if row["with"] is not None:
            s["with"].append(row["with"])
        if row["without"] is not None:
            s["without"].append(row["without"])
        for kind in ("planted", "clean"):
            if kind in tags:
                s[kind][1] += 1
                s[kind][0] += int(row["passed"])
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
    table = {}
    for name, s in sorted(skills.items()):
        w, wo = mean(s["with"]), mean(s["without"])
        table[name] = {"cases": s["cases"], "with": w, "without": wo,
                       "delta": round(w - wo, 3) if w is not None and wo is not None else None,
                       "planted": s["planted"], "clean": s["clean"], "errors": s["errors"], "cost": round(s["cost"], 2)}
    return {"claude_version": result.get("claudeVersion"), "started_at": result.get("startedAt"),
            "plugin_sha": git_sha(root), "partial": bool(result.get("partial")), "ablation": result["suite"].get("ablation"),
            "model": result["suite"].get("model"), "cost": round(result.get("costUsd") or 0, 2),
            "skills": table, "cases": cases}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Summarize a claude plugin eval result per skill.")
    ap.add_argument("result")
    ap.add_argument("--history", help="append one line for this run to this .jsonl file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    s = summarize(result)
    if args.history:
        with open(args.history, "a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in s.items() if k != "cases"}) + "\n")
    if args.json:
        print(json.dumps(s, indent=2))
        return 0
    f = lambda x: "  -  " if x is None else f"{x:5.2f}"
    frac = lambda p: "  -  " if not p[1] else f"{p[0]}/{p[1]}".center(5)
    print(f"{'skill':<26}{'cases':>6}{'with':>7}{'without':>9}{'delta':>7}{'planted':>9}{'clean':>7}{'cost':>8}")
    for name, r in s["skills"].items():
        print(f"{name:<26}{r['cases']:>6}{f(r['with']):>7}{f(r['without']):>9}{f(r['delta']):>7}{frac(r['planted']):>9}{frac(r['clean']):>7}"
              f"{'$' + format(r['cost'], '.2f'):>8}" + (f"   {r['errors']} run error(s)" if r["errors"] else ""))
    print(f"\ntotal ${s['cost']:.2f}, plugin {s['plugin_sha']}, claude {s['claude_version']}" + ("  PARTIAL RUN" if s["partial"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
