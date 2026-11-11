#!/usr/bin/env python3
"""
check_page.py — check a review page against the JSON artifacts it claims to show.

A review page binds every number it shows to a field of an artifact:

    <span data-ref="check-eval.json#/results/0/score" data-fmt=".3f">0.782</span>

This script resolves each binding and fails when the page and the artifact disagree, when an artifact
changed after the page was stamped, when a required block is missing, when the page loads anything from
outside itself, or when it is too long to read in about a minute.

Usage:
    uv run "${CLAUDE_SKILL_DIR}/scripts/check_page.py" <page.html> [--artifacts DIR] [--max-words 350]
                                                        [--strict] [--json]
    uv run "${CLAUDE_SKILL_DIR}/scripts/check_page.py" <page.html> --stamp [--artifacts DIR]

--artifacts  folder the data-ref paths are relative to (default: the page's parent's parent, <out-dir>)
--stamp      write the sha256 of every referenced artifact into the page's sources block, then exit
--strict     numbers that are neither bound (data-ref) nor declared (data-literal) fail instead of warn
--json       print the report as JSON

Exit code 0 when the page passes, 1 when it fails, 2 on a usage error. Reads only; --stamp edits the page.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

PAGES = ("decision", "label", "split", "baseline", "errors", "value", "tried")
BLOCKS = ("decision", "ask", "distrust", "sources")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SOURCES_ID = "review-sources"
SOURCES_RE = re.compile(r'(<script[^>]*\bid="review-sources"[^>]*>)(.*?)(</script>)', re.S)
NUMBER_RE = re.compile(r"(?<![\w.])(?<!\w[-−])[-+−]?\d[\d,]*(?:\.\d+)?%?")  # not the 001 of "run-001"
WORD_RE = re.compile(r"[^\W_]+(?:[-'’.][^\W_]+)*")
MISSING = object()


class Node:
    def __init__(self, tag: str, attrs: dict[str, str], parent: "Node | None"):
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.text: list[str] = []  # every text descendant, in order

    def up(self):
        n = self
        while n is not None:
            yield n
            n = n.parent

    def within(self, test) -> bool:
        return any(test(n) for n in self.up())


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.cur = self.root
        self.nodes: list[Node] = []
        self.visible: list[tuple[Node, str]] = []  # (innermost element, text) outside script/style

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.nodes.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.nodes.append(Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        for n in self.cur.up():
            n.text.append(data)
        if not self.cur.within(lambda n: n.tag in ("script", "style", "template")):
            self.visible.append((self.cur, data))


def text_of(node: Node) -> str:
    return " ".join("".join(node.text).split())


def resolve(doc, pointer: str):
    """RFC 6901 JSON pointer; MISSING when the path does not exist."""
    if pointer in ("", "/"):
        return doc
    if not pointer.startswith("/"):
        return MISSING
    for raw in pointer[1:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(doc, list):
            if not re.fullmatch(r"\d+", key) or int(key) >= len(doc):
                return MISSING
            doc = doc[int(key)]
        elif isinstance(doc, dict):
            if key not in doc:
                return MISSING
            doc = doc[key]
        else:
            return MISSING
    return doc


def parse_number(shown: str) -> tuple[float, int] | None:
    """The number a reader sees and how many decimals it shows; percentages are divided by 100."""
    s = shown.strip().replace(",", "").replace("−", "-").replace(" ", "")
    m = re.fullmatch(r"([-+]?\d+(?:\.(\d+))?)(%?)", s)
    if not m:
        return None
    value, decimals = float(m.group(1)), len(m.group(2) or "")
    return (value / 100, decimals + 2) if m.group(3) else (value, decimals)


def matches(value, shown: str, fmt: str | None) -> tuple[bool, str]:
    """Does the text a reader sees say what the artifact says?"""
    if isinstance(value, bool) or value is None:
        want = json.dumps(value)
        return shown.lower() == want, want
    if isinstance(value, (int, float)):
        if fmt:
            try:
                want = format(value, fmt)
            except (ValueError, TypeError) as e:
                return False, f"bad data-fmt {fmt!r}: {e}"
            return shown.replace("−", "-") == want, want
        parsed = parse_number(shown)
        if parsed is None:
            return False, repr(value)
        seen, decimals = parsed
        if isinstance(value, float) and not math.isfinite(value):
            return False, repr(value)
        return abs(seen - value) <= 0.5 * 10 ** (-decimals) + 1e-12, repr(value)
    return shown == " ".join(str(value).split()), str(value)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_ref(ref: str) -> tuple[str, str]:
    file, _, pointer = ref.partition("#")
    return file.strip(), pointer.strip()


def artifact_path(root: Path, file: str) -> Path | None:
    p = (root / file).resolve()
    return p if p == root or root in p.parents else None


def check(page_path: Path, root: Path, max_words: int, strict: bool) -> dict:
    html = page_path.read_text(encoding="utf-8")
    page = Page()
    page.feed(html)
    page.close()
    errors: list[str] = []
    warnings: list[str] = []

    # ---- the page says what it is ---------------------------------------------------------------
    mains = [n for n in page.nodes if n.tag == "main"]
    kind = mains[0].attrs.get("data-page") if len(mains) == 1 else None
    if len(mains) != 1:
        errors.append(f"expected one <main data-page=...>, found {len(mains)}")
    elif kind not in PAGES:
        errors.append(f"<main data-page={kind!r}> is not one of {', '.join(PAGES)}")
    blocks = {b: [n for n in page.nodes if n.attrs.get("data-block") == b] for b in BLOCKS}
    for b, found in blocks.items():
        if len(found) != 1:
            errors.append(f'expected one data-block="{b}", found {len(found)}')

    # ---- every bound value agrees with its artifact -----------------------------------------------
    docs: dict[str, object] = {}
    used: set[str] = set()
    checked = existence_only = 0
    refs = [n for n in page.nodes if "data-ref" in n.attrs]
    for n in refs:
        ref = n.attrs["data-ref"]
        file, pointer = split_ref(ref)
        path = artifact_path(root, file)
        if path is None:
            errors.append(f"{ref}: path leaves the artifacts folder")
            continue
        if file not in docs:
            try:
                docs[file] = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                docs[file] = MISSING
                errors.append(f"{file}: not found in {root}")
            except json.JSONDecodeError as e:
                docs[file] = MISSING
                errors.append(f"{file}: not JSON ({e.msg})")
        if docs[file] is MISSING:
            continue
        used.add(file)
        value = resolve(docs[file], pointer)
        if value is MISSING:
            errors.append(f"{ref}: no such field")
            continue
        if isinstance(value, (list, dict)) or "data-chart" in n.attrs or n.tag == "svg":
            existence_only += 1  # a chart or a list: the field exists, the drawing is not checked
            continue
        shown = text_of(n)
        ok, want = matches(value, shown, n.attrs.get("data-fmt"))
        if ok:
            checked += 1
        else:
            errors.append(f"{ref}: page shows {shown!r}, artifact has {want}")

    # ---- the decision shown is the artifact's decision --------------------------------------------
    if len(blocks["decision"]) == 1:
        d = blocks["decision"][0]
        if not any(d in n.up() and split_ref(n.attrs["data-ref"])[1].endswith("/decision") for n in refs):
            errors.append('the decision block shows no value bound to an artifact\'s "/decision"')
    if len(blocks["ask"]) == 1:
        asks = [n for n in page.nodes if n.tag == "li" and blocks["ask"][0] in n.up()]
        if not 1 <= len(asks) <= 5:
            errors.append(f"the ask block has {len(asks)} items; give the reviewer one to five things to judge")

    # ---- claims can be cited ----------------------------------------------------------------------
    claims = [n.attrs["data-claim"] for n in page.nodes if "data-claim" in n.attrs]
    for c in sorted({c for c in claims if claims.count(c) > 1}):
        errors.append(f'data-claim="{c}" is used more than once')
    if not claims:
        errors.append("no data-claim ids: a reviewer has nothing to cite")

    # ---- the sources block is current -------------------------------------------------------------
    stamped: dict[str, str] = {}
    m = SOURCES_RE.search(html)
    if not m:
        errors.append(f'no <script type="application/json" id="{SOURCES_ID}"> block (run --stamp)')
    else:
        try:
            stamped = (json.loads(m.group(2) or "{}") or {}).get("files") or {}
        except json.JSONDecodeError:
            errors.append(f"the {SOURCES_ID} block is not JSON (run --stamp)")
    for file in sorted(used):
        now = sha256(artifact_path(root, file))
        if file not in stamped:
            errors.append(f"{file}: referenced but not stamped (run --stamp)")
        elif stamped[file] != now:
            errors.append(f"{file}: changed since the page was stamped; rebuild the page")

    # ---- self-contained ----------------------------------------------------------------------------
    for n in page.nodes:
        for attr in ("src", "poster", "srcset"):
            v = n.attrs.get(attr, "")
            if v and not v.startswith("data:"):
                errors.append(f"<{n.tag} {attr}={v[:60]!r}>: the page must carry its own images and scripts")
        if n.tag == "link" and n.attrs.get("href") and "stylesheet" in n.attrs.get("rel", "") + n.attrs.get("as", ""):
            errors.append(f"<link href={n.attrs['href'][:60]!r}>: inline the stylesheet")
        if n.tag == "style" and re.search(r"@import|url\(\s*['\"]?(?!data:|#)", "".join(n.text)):
            errors.append("<style> loads an outside file (@import or url()): inline it")

    # ---- readable -----------------------------------------------------------------------------------
    html_tag = next((n for n in page.nodes if n.tag == "html"), None)
    if html_tag is None or not html_tag.attrs.get("lang"):
        errors.append("<html> has no lang attribute")
    if not any(n.tag == "title" and text_of(n) for n in page.nodes):
        errors.append("no <title>")
    if not any(n.tag == "meta" and n.attrs.get("name") == "viewport" for n in page.nodes):
        errors.append('no <meta name="viewport">')
    for n in page.nodes:
        if n.tag == "img" and "alt" not in n.attrs:
            errors.append("<img> without alt text")
        outer_svg = n.tag == "svg" and not n.within(lambda a: a is not n and a.tag == "svg")
        if outer_svg or "data-chart" in n.attrs:
            labelled = n.attrs.get("aria-label") or n.attrs.get("aria-labelledby") or n.attrs.get("aria-hidden") == "true"
            if not labelled:
                errors.append(f"<{n.tag}> chart without aria-label (or aria-hidden for decoration)")

    def quiet(n: Node) -> bool:  # text that is not prose the reader has to get through
        return n.tag == "svg" or n.attrs.get("data-block") == "sources" or "data-chart" in n.attrs

    prose = [(n, t) for n, t in page.visible if not n.within(quiet)]
    words = sum(len(WORD_RE.findall(t)) for _, t in prose)
    if words > max_words:
        errors.append(f"{words} words; the limit is {max_words}. Cut, or move detail to the artifact")

    # ---- numbers nobody can trace --------------------------------------------------------------------
    def accounted(n: Node) -> bool:
        return "data-ref" in n.attrs or "data-literal" in n.attrs or n.tag in ("time", "code", "title")

    unbound: list[str] = []
    for n, t in prose:
        if n.within(accounted):
            continue
        for tok in NUMBER_RE.findall(t):
            bare = tok.lstrip("+-−")
            if re.fullmatch(r"\d{1,2}", bare):  # small counts and ordinals: "3 slices", "gate 7"
                continue
            unbound.append(tok)
    literals = [{"text": text_of(n), "why": n.attrs["data-literal"]} for n in page.nodes if "data-literal" in n.attrs]
    for lit in literals:
        if not lit["why"].strip():
            errors.append(f"data-literal on {lit['text']!r} gives no reason")
    if unbound:
        msg = (f"{len(unbound)} number(s) not bound to an artifact: {', '.join(unbound[:8])}"
               f"{' …' if len(unbound) > 8 else ''}. Bind each with data-ref, or declare it with data-literal")
        (errors if strict else warnings).append(msg)

    return {"page": str(page_path), "kind": kind, "ok": not errors, "words": words, "max_words": max_words,
            "refs_checked": checked, "refs_existence_only": existence_only, "claims": len(claims),
            "literals": literals, "unbound_numbers": unbound, "sources": sorted(used),
            "errors": errors, "warnings": warnings}


def stamp(page_path: Path, root: Path) -> int:
    html = page_path.read_text(encoding="utf-8")
    page = Page()
    page.feed(html)
    page.close()
    files: dict[str, str] = {}
    for n in page.nodes:
        if "data-ref" not in n.attrs:
            continue
        file, _ = split_ref(n.attrs["data-ref"])
        path = artifact_path(root, file)
        if path is None or not path.is_file():
            print(f"error: {file}: not found in {root}", file=sys.stderr)
            return 1
        files[file] = sha256(path)
    main = next((n for n in page.nodes if n.tag == "main"), None)
    body = json.dumps({"page": main.attrs.get("data-page") if main else None,
                       "run_id": main.attrs.get("data-run-id") if main else None,
                       "files": dict(sorted(files.items()))}, indent=1)
    if not SOURCES_RE.search(html):
        print(f'error: the page has no <script type="application/json" id="{SOURCES_ID}"> block', file=sys.stderr)
        return 1
    page_path.write_text(SOURCES_RE.sub(lambda m: m.group(1) + "\n" + body + "\n" + m.group(3), html, count=1),
                         encoding="utf-8")
    print(f"stamped {len(files)} artifact(s) into {page_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check a review page against the artifacts it shows.")
    ap.add_argument("page")
    ap.add_argument("--artifacts", help="folder data-ref paths are relative to (default: the page's parent's parent)")
    ap.add_argument("--max-words", type=int, default=350)
    ap.add_argument("--strict", action="store_true", help="unbound numbers fail instead of warn")
    ap.add_argument("--stamp", action="store_true", help="write artifact hashes into the sources block and exit")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    page_path = Path(args.page)
    if not page_path.is_file():
        print(f"error: {page_path} not found", file=sys.stderr)
        return 2
    root = (Path(args.artifacts) if args.artifacts else page_path.resolve().parent.parent).resolve()
    if args.stamp:
        return stamp(page_path, root)
    report = check(page_path, root, args.max_words, args.strict)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{'PASS' if report['ok'] else 'FAIL'}  {page_path.name}  ({report['kind']})  {report['words']} words, "
              f"{report['refs_checked']} values checked, {report['refs_existence_only']} charts or lists bound, "
              f"{len(report['literals'])} declared literals")
        for e in report["errors"]:
            print(f"  error: {e}")
        for w in report["warnings"]:
            print(f"  warning: {w}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
