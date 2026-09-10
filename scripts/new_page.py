#!/usr/bin/env python3
"""Scaffold a new wiki page from its family template.

Usage::

    python3 scripts/new_page.py <family-dir> <slug> --title "..." \\
        [--tags a,b] [--reliability medium] [--sensitivity personal] \\
        [--source raw/x.md ...] [--wiki-root wiki] [--config PATH] \\
        [--today YYYY-MM-DD] [--force] [--dry-run]

``family-dir`` is a key of ``wiki.config.json``'s ``page_families`` (for
example ``entities``). ``slug`` is kebab-case and may be nested, e.g.
``people/ada-lovelace``, which creates the needed subdirectories.

Exit ``0`` on success, ``1`` on any validation problem, with a one-line
reason printed to stderr.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

SLUG_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RELIABILITY_VALUES = ("high", "medium", "low")
SENSITIVITY_VALUES = ("personal", "restricted", "shareable", "public")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DEFAULT_PAGE_FAMILIES = {
    "sources": "source",
    "entities": "entity",
    "concepts": "concept",
    "synthesis": "synthesis",
}

# page_type -> (frontmatter title placeholder, markdown heading placeholder)
TITLE_PLACEHOLDERS = {
    "source": ("<source title>", "<Source title>"),
    "entity": ("<entity name>", "<Entity name>"),
    "concept": ("<concept name>", "<Concept name>"),
    "synthesis": ("<question or topic>", "<Title>"),
}


def load_config(config_path: Path | None, repo_root: Path) -> dict:
    path = config_path if config_path is not None else repo_root / "wiki.config.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def validate_slug(slug: str) -> bool:
    if not slug or slug.startswith("/") or slug.endswith("/") or "//" in slug:
        return False
    return all(SLUG_SEGMENT_RE.match(part) for part in slug.split("/"))


def render_page(
    template_text: str,
    page_type: str,
    title: str,
    today: str,
    tags: list[str],
    reliability: str,
    sensitivity: str,
    sources: list[str] | None,
) -> str:
    text = template_text.replace("<YYYY-MM-DD>", today)

    fm_placeholder, heading_placeholder = TITLE_PLACEHOLDERS[page_type]
    text = text.replace(f'title: "{fm_placeholder}"', "title: " + json.dumps(title))
    text = text.replace(f"# {heading_placeholder}", f"# {title}")

    if tags:
        text = text.replace("tags: []", "tags: [" + ", ".join(tags) + "]")

    text = re.sub(r"(?m)^reliability: \S+$", f"reliability: {reliability}", text, count=1)
    text = re.sub(r"(?m)^sensitivity: \S+$", f"sensitivity: {sensitivity}", text, count=1)

    if sources:
        rendered_sources = ", ".join(json.dumps(s) for s in sources)
        text = re.sub(r"(?m)^sources: \[.*\]$", f"sources: [{rendered_sources}]", text, count=1)
        # The source template's "**Source:**" line links the raw file; fill it
        # from the first raw/ source so the agent only has to add origin and date.
        raw_sources = [s for s in sources if s.startswith("raw/")]
        if raw_sources:
            raw_name = raw_sources[0][len("raw/"):]
            text = text.replace("[<file>](../raw/<file>)", f"[{raw_name}](../raw/{raw_name})", 1)

    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new wiki page from a template.")
    parser.add_argument("family", help="page family directory, e.g. entities")
    parser.add_argument("slug", help="kebab-case slug, may be nested (people/ada-lovelace)")
    parser.add_argument("--title")
    parser.add_argument("--tags", default="", help="comma-separated tags, e.g. --tags pattern,knowledge")
    parser.add_argument("--reliability", default="medium")
    parser.add_argument("--sensitivity", default="personal")
    parser.add_argument("--source", action="append", dest="sources", default=None)
    parser.add_argument("--wiki-root", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--today", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path.cwd()
    config = load_config(Path(args.config) if args.config else None, repo_root)
    page_families = config.get("page_families") or DEFAULT_PAGE_FAMILIES

    if args.family not in page_families:
        known = ", ".join(sorted(page_families))
        print(f"new_page: unknown family '{args.family}' (known: {known})", file=sys.stderr)
        return 1

    page_type = page_families[args.family]
    if page_type not in TITLE_PLACEHOLDERS:
        print(f"new_page: no template mapping for page_type '{page_type}'", file=sys.stderr)
        return 1

    if not args.title:
        print("new_page: --title is required", file=sys.stderr)
        return 1

    if not validate_slug(args.slug):
        print(
            f"new_page: invalid slug '{args.slug}' "
            "(expected lowercase kebab-case, optionally nested with '/')",
            file=sys.stderr,
        )
        return 1

    if args.reliability not in RELIABILITY_VALUES:
        print(
            f"new_page: invalid --reliability '{args.reliability}' "
            f"(expected one of {', '.join(RELIABILITY_VALUES)})",
            file=sys.stderr,
        )
        return 1

    if args.sensitivity not in SENSITIVITY_VALUES:
        print(
            f"new_page: invalid --sensitivity '{args.sensitivity}' "
            f"(expected one of {', '.join(SENSITIVITY_VALUES)})",
            file=sys.stderr,
        )
        return 1

    today = args.today or date.today().isoformat()
    if not DATE_RE.match(today):
        print(f"new_page: invalid --today '{today}' (expected YYYY-MM-DD)", file=sys.stderr)
        return 1

    wiki_root_name = args.wiki_root or config.get("wiki_root", "wiki")
    wiki_root = repo_root / wiki_root_name

    template_path = wiki_root / "_templates" / f"{page_type}.md"
    try:
        template_text = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"new_page: cannot read template {template_path}: {exc}", file=sys.stderr)
        return 1

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []

    target_path = wiki_root / args.family / f"{args.slug}.md"

    if not args.dry_run and target_path.exists() and not args.force:
        print(
            f"new_page: refusing to overwrite existing page {target_path} (use --force)",
            file=sys.stderr,
        )
        return 1

    content = render_page(
        template_text,
        page_type,
        args.title,
        today,
        tags,
        args.reliability,
        args.sensitivity,
        args.sources,
    )

    if args.dry_run:
        print(content, end="")
        return 0

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    print(str(target_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
