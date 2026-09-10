#!/usr/bin/env python3
"""Stdlib BM25 search over wiki content pages.

Indexes every ``*.md`` file under the configured page-family directories
(``sources``, ``entities``, ``concepts``, ``synthesis`` by default),
excluding support files (``README.md``, ``CLAUDE.md``, ``AGENTS.md``),
``INDEX*``/``LOG*`` files and anything under ``raw/`` or ``_templates/``.

Field weighting (title x3, tags x2, headings x2, body x1) is implemented by
repeating each field's tokens the corresponding number of times before
counting term frequencies, so BM25 runs over one combined bag of words per
document.

CLI::

    python3 scripts/wiki_search.py "query" [--wiki-root wiki] [--config PATH]
        [--top 10] [--format text|json]

Prints ``no matches`` and exits ``0`` when the wiki is empty or nothing
matches. Public API: ``build_index(wiki_root, config) -> Index`` and
``search(index, query, top) -> list[dict]``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

K1 = 1.5
B = 0.75

SUPPORT_BASENAMES = {"README.md", "CLAUDE.md", "AGENTS.md"}
EXCLUDED_DIR_PARTS = {"raw", "_templates"}

DEFAULT_PAGE_FAMILIES = {
    "sources": "source",
    "entities": "entity",
    "concepts": "concept",
    "synthesis": "synthesis",
}

TOKEN_RE = re.compile(r"\w+", re.UNICODE)
HEADING_RE = re.compile(r"(?m)^#{1,6}\s+(.*)$")


@dataclass
class Doc:
    path: str
    slug: str
    title: str
    term_freqs: dict = field(default_factory=dict)
    length: int = 0


@dataclass
class Index:
    docs: list = field(default_factory=list)
    doc_freq: dict = field(default_factory=dict)
    avg_doc_length: float = 0.0
    n_docs: int = 0


def tokenize(text: str) -> list[str]:
    tokens = TOKEN_RE.findall(text.lower())
    tokens = [t for t in tokens if len(t) >= 2]
    stemmed = []
    for t in tokens:
        if len(t) > 4 and t.endswith("s"):
            t = t[:-1]
        stemmed.append(t)
    return stemmed


def _load_config(config_path: Path | None, repo_root: Path) -> dict:
    path = config_path if config_path is not None else repo_root / "wiki.config.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse_page(text: str) -> tuple[dict, str]:
    """Split a page into (frontmatter dict, body text)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    frontmatter: dict = {}
    body_start = len(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start = i + 1
            break
        m = re.match(r"^(\w+):\s*(.*)$", lines[i])
        if m:
            frontmatter[m.group(1)] = m.group(2).strip()
    body = "\n".join(lines[body_start:])
    return frontmatter, body


def parse_tags(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    if not raw.strip():
        return []
    parts = [p.strip().strip('"').strip("'") for p in raw.split(",")]
    return [p for p in parts if p]


def _iter_pages(wiki_root: Path, page_families: dict) -> list[tuple[str, Path]]:
    pages = []
    for family in sorted(page_families):
        family_dir = wiki_root / family
        if not family_dir.is_dir():
            continue
        for path in sorted(family_dir.rglob("*.md")):
            if path.name in SUPPORT_BASENAMES:
                continue
            if path.name.startswith("INDEX") or path.name.startswith("LOG"):
                continue
            if EXCLUDED_DIR_PARTS.intersection(path.relative_to(wiki_root).parts):
                continue
            pages.append((family, path))
    return pages


def build_index(wiki_root: Path, config: dict) -> Index:
    page_families = config.get("page_families") or DEFAULT_PAGE_FAMILIES

    docs: list[Doc] = []
    doc_freq: dict = {}
    total_length = 0

    for family, path in _iter_pages(wiki_root, page_families):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        frontmatter, body = parse_page(text)
        title = frontmatter.get("title", "").strip().strip('"').strip("'") or path.stem
        tags = parse_tags(frontmatter.get("tags", "[]"))
        headings = HEADING_RE.findall(body)

        weighted_tokens: list[str] = []
        weighted_tokens += tokenize(title) * 3
        weighted_tokens += tokenize(" ".join(tags)) * 2
        weighted_tokens += tokenize(" ".join(headings)) * 2
        weighted_tokens += tokenize(body) * 1

        term_freqs: dict = {}
        for tok in weighted_tokens:
            term_freqs[tok] = term_freqs.get(tok, 0) + 1

        length = len(weighted_tokens)
        total_length += length

        family_dir = wiki_root / family
        slug = path.relative_to(family_dir).with_suffix("").as_posix()

        docs.append(
            Doc(path=path.relative_to(wiki_root).as_posix(), slug=slug, title=title, term_freqs=term_freqs, length=length)
        )
        for term in term_freqs:
            doc_freq[term] = doc_freq.get(term, 0) + 1

    n_docs = len(docs)
    avg_doc_length = (total_length / n_docs) if n_docs else 0.0

    return Index(docs=docs, doc_freq=doc_freq, avg_doc_length=avg_doc_length, n_docs=n_docs)


def search(index: Index, query: str, top: int = 10) -> list[dict]:
    seen = set()
    query_terms = []
    for t in tokenize(query):
        if t not in seen:
            seen.add(t)
            query_terms.append(t)
    if not query_terms or index.n_docs == 0:
        return []

    results = []
    for doc in index.docs:
        score = 0.0
        matched = []
        for term in query_terms:
            tf = doc.term_freqs.get(term, 0)
            if tf <= 0:
                continue
            matched.append(term)
            df = index.doc_freq.get(term, 0)
            idf = math.log(1 + (index.n_docs - df + 0.5) / (df + 0.5))
            norm_len = (doc.length / index.avg_doc_length) if index.avg_doc_length else 1.0
            denom = tf + K1 * (1 - B + B * norm_len)
            score += idf * (tf * (K1 + 1)) / denom
        if score > 0:
            results.append(
                {
                    "path": doc.path,
                    "slug": doc.slug,
                    "title": doc.title,
                    "score": score,
                    "matched_terms": matched,
                }
            )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BM25 search over wiki content pages.")
    parser.add_argument("query")
    parser.add_argument("--wiki-root", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    repo_root = Path.cwd()
    config = _load_config(Path(args.config) if args.config else None, repo_root)
    wiki_root_name = args.wiki_root or config.get("wiki_root", "wiki")
    wiki_root = Path(wiki_root_name)
    if not wiki_root.is_absolute():
        wiki_root = repo_root / wiki_root_name

    index = build_index(wiki_root, config)
    results = search(index, args.query, top=args.top)

    if not results:
        print("no matches")
        return 0

    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False))
    else:
        for r in results:
            print(f"{r['score']:6.2f}  {r['path']}  — {r['title']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
