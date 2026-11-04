#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Record what produced a result: git state, environment, lockfiles, data hashes, seed, split.

Standard library only. Run it with the PROJECT's interpreter so package versions reflect the
training environment, e.g. `uv run python provenance.py ...` or `.venv/bin/python provenance.py ...`.
(`uv run provenance.py` would run in an isolated environment and miss the project's packages.)

Output JSON fields: created_at, cwd, git {sha, dirty, untracked_files, diff_sha256, branch,
remote_url}, env {python, executable, platform, in_virtualenv, packages}, lockfiles [{path, sha256}],
data [{path, bytes, sha256, modified, hash_mode}], seed, split_manifest {path, sha256,
test_keys_sha256}, warnings.

Data hashing: files are hashed in full, except files over 2 GB, which hash the size plus the
first and last 64 MB (hash_mode "partial"). Directories get a manifest hash over the sorted
(relpath, size, sha256) of every file (hash_mode "manifest").

Without --out the JSON goes to stdout.

Examples:
  uv run python provenance.py --data data/train.parquet --seed 42 \\
      --split-manifest out/splits/split-manifest.json --out out/provenance.json
  .venv/bin/python provenance.py --data data/ --packages sentence-transformers,optuna
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

DEFAULT_PACKAGES = ["numpy", "pandas", "polars", "scikit-learn", "scipy", "torch", "transformers", "datasets",
                    "accelerate", "peft", "trl", "lightgbm", "xgboost", "catboost", "shap", "mlflow", "wandb"]
LOCKFILE_PATTERNS = ["uv.lock", "poetry.lock", "requirements*.txt", "environment.yml", "environment.yaml",
                     "Pipfile.lock", "pyproject.toml"]
PARTIAL_THRESHOLD = 2 * 1024**3
PARTIAL_CHUNK = 64 * 1024**2


def utc(ts: float | None = None) -> str:
    dt = datetime.now(timezone.utc) if ts is None else datetime.fromtimestamp(ts, timezone.utc)
    return dt.isoformat(timespec="seconds")


def git(args: list[str], cwd: Path) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def strip_credentials(url: str | None) -> str | None:
    """Drop user:password@ from http(s) URLs and the password from other URL schemes."""
    if not url or "://" not in url:
        return url  # scp-style git@host:org/repo carries no secret
    p = urlsplit(url)
    if "@" not in p.netloc:
        return url
    userinfo, host = p.netloc.rsplit("@", 1)
    if p.scheme not in ("http", "https", "ftp", "ftps"):
        host = f"{userinfo.split(':', 1)[0]}@{host}"
    return urlunsplit((p.scheme, host, p.path, p.query, p.fragment))


def git_info(repo: Path) -> tuple[dict | None, Path | None]:
    root = git(["rev-parse", "--show-toplevel"], repo)
    if root is None:
        return None, None
    root_p = Path(root)
    sha = git(["rev-parse", "HEAD"], root_p)
    status = git(["status", "--porcelain", "--untracked-files=all"], root_p) or ""
    lines = [ln for ln in status.splitlines() if ln]
    tracked = [ln for ln in lines if not ln.startswith("??")]
    diff_sha = None
    if tracked and sha:
        try:
            diff = subprocess.run(["git", "diff", "HEAD", "--binary"], cwd=root_p, capture_output=True, timeout=60, check=False)
            diff_sha = hashlib.sha256(diff.stdout).hexdigest() if diff.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            pass
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], root_p)
    remote = git(["remote", "get-url", "origin"], root_p)
    if remote is None:
        remotes = (git(["remote"], root_p) or "").split()
        remote = git(["remote", "get-url", remotes[0]], root_p) if remotes else None
    return {"root": str(root_p), "sha": sha, "dirty": bool(tracked), "untracked_files": len(lines) - len(tracked),
            "diff_sha256": diff_sha, "branch": None if branch == "HEAD" else branch,
            "remote_url": strip_credentials(remote)}, root_p


def sha256_file(path: Path, size: int) -> tuple[str, str]:
    """(hex digest, hash_mode). Files over 2 GB: size + first and last 64 MB."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        if size > PARTIAL_THRESHOLD:
            h.update(str(size).encode() + b"\n")
            h.update(f.read(PARTIAL_CHUNK))
            f.seek(size - PARTIAL_CHUNK)
            h.update(f.read(PARTIAL_CHUNK))
            return h.hexdigest(), "partial"
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest(), "full"


def hash_data(path: Path) -> dict:
    if path.is_file():
        st = path.stat()
        digest, mode = sha256_file(path, st.st_size)
        return {"path": str(path.resolve()), "bytes": st.st_size, "sha256": digest,
                "modified": utc(st.st_mtime), "hash_mode": mode}
    lines, total, latest, partial = [], 0, 0.0, False
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames.sort()
        for name in sorted(filenames):
            fp = Path(dirpath, name)
            if not fp.is_file():
                continue
            st = fp.stat()
            digest, mode = sha256_file(fp, st.st_size)
            partial |= mode == "partial"
            total += st.st_size
            latest = max(latest, st.st_mtime)
            lines.append(f"{fp.relative_to(path).as_posix()}\t{st.st_size}\t{digest}")
    lines.sort()
    return {"path": str(path.resolve()), "bytes": total,
            "sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest(),
            "modified": utc(latest) if lines else None, "hash_mode": "manifest", "n_files": len(lines),
            "contains_partial_hashes": partial}


def find_lockfiles(dirs: list[Path]) -> list[dict]:
    seen, out = set(), []
    for d in dirs:
        for pat in LOCKFILE_PATTERNS:
            for p in sorted(glob.glob(str(d / pat))):
                rp = Path(p).resolve()
                if rp in seen or not rp.is_file():
                    continue
                seen.add(rp)
                out.append({"path": str(rp), "sha256": sha256_file(rp, rp.stat().st_size)[0]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", nargs="+", action="extend", default=[], type=Path,
                    help="data files or directories to hash (repeatable)")
    ap.add_argument("--seed", type=int, help="random seed used by the run")
    ap.add_argument("--split-manifest", type=Path, help="split-manifest.json from make_splits.py")
    ap.add_argument("--packages", help="extra comma-separated distribution names to record")
    ap.add_argument("--repo", type=Path, default=Path.cwd(), help="directory inside the git repo (default: cwd)")
    ap.add_argument("--out", type=Path, help="output JSON path (default: stdout)")
    args = ap.parse_args(argv)

    missing = [str(p) for p in args.data if not p.exists()]
    if missing:
        print(f"error: data path(s) not found: {missing}", file=sys.stderr)
        return 2
    if args.split_manifest and not args.split_manifest.is_file():
        print(f"error: split manifest not found: {args.split_manifest}", file=sys.stderr)
        return 2

    warns: list[str] = []
    try:
        gi, root = git_info(args.repo)
    except Exception as e:  # noqa: BLE001 - provenance must never fail on git
        gi, root = None, None
        warns.append(f"git info unavailable: {e}")
    if gi is None:
        warns.append(f"{args.repo} is not inside a git repository (or git is unavailable)")
    elif gi["dirty"]:
        warns.append("working tree has uncommitted changes to tracked files; the commit sha alone does not "
                     "reproduce this result (see git.diff_sha256)")

    names = DEFAULT_PACKAGES + [p.strip() for p in (args.packages or "").split(",") if p.strip()]
    packages = {}
    for name in dict.fromkeys(names):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    if not any(n in packages for n in DEFAULT_PACKAGES):
        warns.append(f"none of the default ML packages are importable from {sys.executable}; if the project uses "
                     "them, rerun with its interpreter (`uv run python provenance.py` or `.venv/bin/python ...`), "
                     "not `uv run provenance.py`, which uses an isolated environment")

    split = None
    if args.split_manifest:
        mp = args.split_manifest
        try:
            test_hash = json.loads(mp.read_text()).get("test_keys_sha256")
        except (OSError, ValueError):
            test_hash = None
            warns.append(f"could not read test_keys_sha256 from {mp}")
        split = {"path": str(mp.resolve()), "sha256": sha256_file(mp, mp.stat().st_size)[0],
                 "test_keys_sha256": test_hash}

    lock_dirs = [d for d in (root, Path.cwd()) if d is not None]
    out = {
        "created_at": utc(),
        "cwd": str(Path.cwd()),
        "git": gi,
        "env": {"python": platform.python_version(), "executable": sys.executable, "platform": platform.platform(),
                "in_virtualenv": sys.prefix != sys.base_prefix, "packages": packages},
        "lockfiles": find_lockfiles(lock_dirs),
        "data": [hash_data(p) for p in args.data],
        "seed": args.seed,
        "split_manifest": split,
        "warnings": warns,
    }
    text = json.dumps(out, indent=2) + "\n"
    if not args.out:
        sys.stdout.write(text)
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    g = out["git"]
    print(f"provenance -> {args.out}")
    print(f"  git: {g['sha'][:12] if g and g['sha'] else 'n/a'}{' (dirty)' if g and g['dirty'] else ''}"
          f" on {g['branch'] if g else 'n/a'}")
    print(f"  python {out['env']['python']} ({sys.executable}); {len(packages)} packages recorded")
    print(f"  lockfiles: {len(out['lockfiles'])}; data: "
          + (", ".join(f"{Path(d['path']).name} {d['sha256'][:12]} ({d['hash_mode']})" for d in out["data"]) or "none"))
    for w in warns:
        print(f"  WARNING: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
