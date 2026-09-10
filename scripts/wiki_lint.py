#!/usr/bin/env python3
"""Deterministic health lint for the LLM wiki.

Scans the wiki tree for the mechanically-checkable rules in ``wiki/CLAUDE.md``:
required frontmatter, enum values, page-type-vs-directory agreement, size caps,
broken wikilinks, duplicate slugs, dangling raw source references, index
membership and duplicates, leaked frontmatter, orphan pages, staleness, and
leftover template placeholders. It never edits anything; it only reports.

Python 3.9+ standard library only.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
import re
import sys


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "page_families": {
        "sources": "source",
        "entities": "entity",
        "concepts": "concept",
        "synthesis": "synthesis",
    },
    "caps": {"soft_lines": 400, "hard_lines": 800},
    "index": {"root": "INDEX.md", "shard_prefix": "INDEX-"},
    "staleness_days": {
        "low_reliability": 30,
        "pending_review": 30,
        "cold_page": 180,
    },
    "scale_thresholds": {
        "shard_index_at_pages": 150,
        "search_step_at_pages": 300,
        "subdivide_directory_at_pages": 50,
    },
    "privacy": {"staging_dir": ".staging"},
}

RELIABILITY_VALUES = ("high", "medium", "low")
SENSITIVITY_VALUES = ("personal", "restricted", "shareable", "public")
REQUIRED_FRONTMATTER_FIELDS = (
    "title",
    "page_type",
    "reliability",
    "sensitivity",
    "sources",
    "created",
    "updated",
)
EXCLUDED_BASENAMES = {
    "readme.md",
    "claude.md",
    "agents.md",
    "_template.md",
    "template.md",
}
EXCLUDED_DIR_PARTS = {"_templates", "raw"}

ERROR_KEYS = (
    "missing_frontmatter",
    "invalid_enum",
    "invalid_date",
    "page_type_mismatches",
    "hard_cap_exceeded",
    "broken_wikilinks",
    "duplicate_slugs",
    "broken_source_references",
    "missing_index_entries",
    "duplicate_index_entries",
    "frontmatter_leaked_into_body",
    "config_invalid",
)

WARNING_KEYS = (
    "orphans",
    "soft_cap_exceeded",
    "stale_low_reliability",
    "stale_pending_review",
    "cold_pages",
    "template_placeholders",
)


class ConfigError(ValueError):
    """Raised when wiki.config.json exists but is malformed."""


# --------------------------------------------------------------------------
# Regex toolkit (ported and extended from the reference page_inventory.py)
# --------------------------------------------------------------------------

_FRONTMATTER_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$")
_WIKILINK = re.compile(r"\[\[([^\[\]\n]+)\]\]")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_CLOSING_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})[ \t]*$")
_INLINE_CODE = re.compile(r"(`+)(.*?)\1")
_RAW_REFERENCE = re.compile(r"(?<![A-Za-z0-9_./-])((?:wiki/)?raw/[^\s,\]\}\"']+)")
_LEAKED_FRONTMATTER_ITEM = re.compile(
    r'^\s+- "(?:(?:wiki/)?(?:sources|raw)/[^"]+|conversation:[^"]+)"\s*$'
)
_INDEX_BULLET = re.compile(r"^\s*[-*+]\s+")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PENDING_REVIEW_HEADING = re.compile(r"^#{1,6}\s+Pending Review\s*$")
_HEADING = re.compile(r"^#{1,6}\s+")
_PLACEHOLDER_ANGLE = re.compile(r"<[A-Za-z][A-Za-z0-9 _-]*>")
_PLACEHOLDER_BRACE = re.compile(r"\{\{[A-Z_]+\}\}")
_WHOLE_LINE_PLACEHOLDER = re.compile(r"^<.+>$")


@dataclass(frozen=True)
class PageRecord:
    path: Path
    page_type: str
    dirname: str
    slug: str


@dataclass(frozen=True)
class WikiLink:
    raw: str
    target: str
    line: int


class _ArgParser(argparse.ArgumentParser):
    """argparse that reports usage errors as 'could not run' (exit 1)."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


# --------------------------------------------------------------------------
# Config loading
# --------------------------------------------------------------------------

def _default_config() -> dict:
    return json.loads(json.dumps(DEFAULT_CONFIG))


def resolve_config_path(path_or_none, wiki_root) -> Path:
    if path_or_none is not None:
        return Path(path_or_none)
    return Path(wiki_root).parent / "wiki.config.json"


def _is_str_dict(value) -> bool:
    return isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    )


def _is_plain_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _merge_and_validate(data) -> dict:
    if not isinstance(data, dict):
        raise ConfigError("config root must be a JSON object")

    config = _default_config()

    if "page_families" in data:
        value = data["page_families"]
        if not _is_str_dict(value) or not value:
            raise ConfigError("page_families must be a non-empty object of string to string")
        config["page_families"] = dict(value)

    if "caps" in data:
        value = data["caps"]
        if not isinstance(value, dict):
            raise ConfigError("caps must be an object")
        for key in ("soft_lines", "hard_lines"):
            if key in value:
                if not _is_plain_int(value[key]) or value[key] <= 0:
                    raise ConfigError(f"caps.{key} must be a positive integer")
                config["caps"][key] = value[key]

    if "index" in data:
        value = data["index"]
        if not isinstance(value, dict):
            raise ConfigError("index must be an object")
        for key in ("root", "shard_prefix"):
            if key in value:
                if not isinstance(value[key], str) or not value[key]:
                    raise ConfigError(f"index.{key} must be a non-empty string")
                config["index"][key] = value[key]

    if "staleness_days" in data:
        value = data["staleness_days"]
        if not isinstance(value, dict):
            raise ConfigError("staleness_days must be an object")
        for key in ("low_reliability", "pending_review", "cold_page"):
            if key in value:
                if not _is_plain_int(value[key]) or value[key] < 0:
                    raise ConfigError(f"staleness_days.{key} must be a non-negative integer")
                config["staleness_days"][key] = value[key]

    if "scale_thresholds" in data:
        value = data["scale_thresholds"]
        if not isinstance(value, dict):
            raise ConfigError("scale_thresholds must be an object")
        for key in (
            "shard_index_at_pages",
            "search_step_at_pages",
            "subdivide_directory_at_pages",
        ):
            if key in value:
                if not _is_plain_int(value[key]) or value[key] <= 0:
                    raise ConfigError(f"scale_thresholds.{key} must be a positive integer")
                config["scale_thresholds"][key] = value[key]

    if "privacy" in data:
        value = data["privacy"]
        if not isinstance(value, dict):
            raise ConfigError("privacy must be an object")
        if "staging_dir" in value:
            if not isinstance(value["staging_dir"], str) or not value["staging_dir"]:
                raise ConfigError("privacy.staging_dir must be a non-empty string")
            config["privacy"]["staging_dir"] = value["staging_dir"]

    return config


def load_config(path_or_none, wiki_root) -> dict:
    """Load wiki.config.json, falling back to shipped defaults when absent."""
    config_path = resolve_config_path(path_or_none, wiki_root)
    if not config_path.is_file():
        return _default_config()
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"could not read {config_path}: {error}") from error
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ConfigError(f"invalid JSON in {config_path}: {error}") from error
    return _merge_and_validate(data)


# --------------------------------------------------------------------------
# Low-level text helpers (fence/inline-code aware)
# --------------------------------------------------------------------------

def _iter_lines_outside_fences(text: str):
    """Yield (line_number, raw_line) for every line not inside a fenced block."""
    fence_character = ""
    fence_length = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        fence_match = (
            _CLOSING_FENCE.match(line) if fence_character else _FENCE.match(line)
        )
        if fence_match:
            marker = fence_match.group(1)
            if not fence_character:
                fence_character = marker[0]
                fence_length = len(marker)
                continue
            if marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = ""
                fence_length = 0
                continue
        if fence_character:
            continue
        yield line_number, line


def _iter_visible_lines(text: str):
    """Like _iter_lines_outside_fences but with inline code spans blanked out."""
    for line_number, line in _iter_lines_outside_fences(text):
        visible = _INLINE_CODE.sub(lambda match: " " * len(match.group(0)), line)
        yield line_number, visible


def _normalize_wikilink_target(value: str) -> str:
    target = value.split("|", 1)[0].split("#", 1)[0].strip()
    target = target.replace("\\", "/")
    while target.startswith("./"):
        target = target[2:]
    target = target.lstrip("/")
    if target.startswith("wiki/"):
        target = target[5:]
    if target.casefold().endswith(".md"):
        target = target[:-3]
    return target.strip()


def extract_wikilinks(text: str) -> tuple:
    """Extract [[wikilinks]] with line numbers, ignoring fences and inline code."""
    links = []
    for line_number, visible_line in _iter_visible_lines(text):
        for match in _WIKILINK.finditer(visible_line):
            target = _normalize_wikilink_target(match.group(1))
            if target:
                links.append(WikiLink(raw=match.group(0), target=target, line=line_number))
    return tuple(links)


def _primary_index_entries(text: str) -> tuple:
    """Bullets of the form `- [[target]]` (the link starts the bullet content)."""
    entries = []
    for line_number, visible_line in _iter_visible_lines(text):
        bullet = _INDEX_BULLET.match(visible_line)
        if not bullet:
            continue
        content = visible_line[bullet.end():]
        match = _WIKILINK.match(content)
        if not match:
            continue
        target = _normalize_wikilink_target(match.group(1))
        if target:
            entries.append(WikiLink(raw=match.group(0), target=target, line=line_number))
    return tuple(entries)


def _parse_frontmatter(text: str) -> dict:
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    closing_line = None
    for position in range(1, len(lines)):
        if lines[position].strip() == "---":
            closing_line = position
            break
    if closing_line is None:
        return {}

    fields = {}
    current_key = ""
    values = []
    for line in lines[1:closing_line]:
        match = _FRONTMATTER_KEY.match(line)
        if match:
            if current_key:
                fields[current_key] = "\n".join(values).strip()
            current_key = match.group(1)
            values = [match.group(2) or ""]
        elif current_key:
            values.append(line)
    if current_key:
        fields[current_key] = "\n".join(values).strip()
    return fields


def _unquote_scalar(value: str):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _raw_references(sources_value: str) -> tuple:
    references = set()
    for match in _RAW_REFERENCE.finditer(sources_value):
        reference = match.group(1).rstrip(".)")
        if reference.startswith("wiki/"):
            reference = reference[5:]
        references.add(reference)
    return tuple(sorted(references))


def _leaked_frontmatter_items(text: str) -> tuple:
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return ()
    closing_line = None
    for position in range(1, len(lines)):
        if lines[position].strip() == "---":
            closing_line = position
            break
    if closing_line is None:
        return ()

    body = "\n".join(lines[closing_line + 1:])
    findings = []
    for line_number, line in _iter_lines_outside_fences(body):
        if _LEAKED_FRONTMATTER_ITEM.match(line):
            findings.append({"line": closing_line + 1 + line_number, "text": line.strip()})
    return tuple(findings)


def _find_placeholders(text: str) -> list:
    found = []
    for _line_number, visible_line in _iter_visible_lines(text):
        for match in _PLACEHOLDER_ANGLE.finditer(visible_line):
            found.append(match.group(0))
        for match in _PLACEHOLDER_BRACE.finditer(visible_line):
            found.append(match.group(0))
    return found


def _is_placeholder_only_line(stripped: str) -> bool:
    """A whole line that is a single <...> blurb, optionally as a bullet item."""
    if _WHOLE_LINE_PLACEHOLDER.match(stripped):
        return True
    bullet = _INDEX_BULLET.match(stripped)
    if bullet and _WHOLE_LINE_PLACEHOLDER.match(stripped[bullet.end():].strip()):
        return True
    return False


def _pending_review_has_content(text: str) -> bool:
    """True when a '## Pending Review' section holds a real, non-placeholder line.

    A whole line wrapped in a single angle-bracket span (the shipped templates'
    "<Unverified or contradicted claims. Delete the section if empty.>" style
    of placeholder) does not count as content, even though it may contain
    punctuation the shorter `template_placeholders` regex does not match.
    """
    in_section = False
    for line in text.splitlines():
        if _PENDING_REVIEW_HEADING.match(line.strip()):
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if _HEADING.match(stripped):
                break
            if not stripped:
                continue
            if _is_placeholder_only_line(stripped):
                continue
            return True
    return False


def _parse_date(value: str):
    if not _DATE_RE.match(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------

def _relative(wiki_root: Path, path: Path) -> str:
    return path.relative_to(wiki_root).as_posix()


def discover_content_pages(wiki_root: Path, config: dict) -> tuple:
    """Discover every content page under a page-family directory, recursively."""
    wiki_root = Path(wiki_root)
    pages = []
    for dirname, page_type in config["page_families"].items():
        directory = wiki_root / dirname
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.casefold() != ".md":
                continue
            if path.name.casefold() in EXCLUDED_BASENAMES:
                continue
            relative_parts = path.relative_to(wiki_root).parts
            if EXCLUDED_DIR_PARTS.intersection(relative_parts):
                continue
            if path.name.upper().startswith("INDEX") or path.name.casefold() == "log.md":
                continue
            pages.append(
                PageRecord(path=path, page_type=page_type, dirname=dirname, slug=path.stem)
            )
    return tuple(sorted(pages, key=lambda page: _relative(wiki_root, page.path)))


def discover_index_documents(wiki_root: Path, config: dict) -> tuple:
    """Return root INDEX*.md documents (the hub plus any page-type shards)."""
    wiki_root = Path(wiki_root)
    if not wiki_root.is_dir():
        return ()
    root_name = config["index"]["root"]
    shard_prefix = config["index"]["shard_prefix"]
    paths = [
        path
        for path in wiki_root.iterdir()
        if path.is_file()
        and path.suffix.casefold() == ".md"
        and (path.name == root_name or path.name.startswith(shard_prefix))
    ]
    return tuple(sorted(paths, key=lambda path: _relative(wiki_root, path)))


def discover_target_documents(wiki_root: Path) -> tuple:
    """Every file under wiki_root: valid wikilink targets, content or not."""
    wiki_root = Path(wiki_root)
    if not wiki_root.is_dir():
        return ()
    paths = (path for path in wiki_root.rglob("*") if path.is_file())
    return tuple(sorted(paths, key=lambda path: _relative(wiki_root, path)))


def _target_keys(wiki_root: Path, documents: tuple) -> set:
    keys = set()
    for path in documents:
        relative = _relative(wiki_root, path)
        keys.add(relative)
        keys.add(path.name)
        if path.suffix.casefold() == ".md":
            keys.add(relative[:-3])
            keys.add(path.stem)
    return keys


def _page_link_keys(wiki_root: Path, page: PageRecord) -> set:
    relative = _relative(wiki_root, page.path)
    return {page.slug, relative, relative[:-3]}


# --------------------------------------------------------------------------
# Report building
# --------------------------------------------------------------------------

def build_report(wiki_root: Path, config: dict, today: date) -> dict:
    """Build the full, JSON-stable lint report. Never raises on page content."""
    wiki_root = Path(wiki_root)
    soft_lines = config["caps"]["soft_lines"]
    hard_lines = config["caps"]["hard_lines"]

    pages = discover_content_pages(wiki_root, config)
    index_documents = discover_index_documents(wiki_root, config)
    target_documents = discover_target_documents(wiki_root)
    target_keys = _target_keys(wiki_root, target_documents)

    counts = {dirname: 0 for dirname in config["page_families"]}
    for page in pages:
        counts[page.dirname] += 1
    counts["total"] = len(pages)

    errors = {key: [] for key in ERROR_KEYS}
    warnings = {key: [] for key in WARNING_KEYS}

    texts = {}
    line_counts = {}
    frontmatters = {}
    reliability_distribution = {value: 0 for value in RELIABILITY_VALUES}
    reliability_distribution["unknown"] = 0
    sensitivity_distribution = {value: 0 for value in SENSITIVITY_VALUES}
    sensitivity_distribution["unknown"] = 0
    page_type_values = set(config["page_families"].values())

    for page in pages:
        try:
            text = page.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            text = ""
        texts[page.path] = text
        relative = _relative(wiki_root, page.path)

        frontmatter = _parse_frontmatter(text)
        frontmatters[page.path] = frontmatter

        missing = sorted(
            field
            for field in REQUIRED_FRONTMATTER_FIELDS
            if not frontmatter.get(field, "").strip()
        )
        if missing:
            errors["missing_frontmatter"].append({"path": relative, "missing": missing})

        if frontmatter.get("page_type", "").strip():
            actual = _unquote_scalar(frontmatter["page_type"])
            if actual not in page_type_values:
                errors["invalid_enum"].append(
                    {"path": relative, "field": "page_type", "value": actual}
                )
            if actual != page.page_type:
                errors["page_type_mismatches"].append(
                    {"path": relative, "expected": page.page_type, "actual": actual}
                )

        if frontmatter.get("reliability", "").strip():
            actual = _unquote_scalar(frontmatter["reliability"])
            if actual in reliability_distribution:
                reliability_distribution[actual] += 1
            else:
                reliability_distribution["unknown"] += 1
                errors["invalid_enum"].append(
                    {"path": relative, "field": "reliability", "value": actual}
                )
        else:
            reliability_distribution["unknown"] += 1

        if frontmatter.get("sensitivity", "").strip():
            actual = _unquote_scalar(frontmatter["sensitivity"])
            if actual in sensitivity_distribution:
                sensitivity_distribution[actual] += 1
            else:
                sensitivity_distribution["unknown"] += 1
                errors["invalid_enum"].append(
                    {"path": relative, "field": "sensitivity", "value": actual}
                )
        else:
            sensitivity_distribution["unknown"] += 1

        for field in ("created", "updated"):
            if frontmatter.get(field, "").strip():
                raw_value = _unquote_scalar(frontmatter[field])
                if _parse_date(raw_value) is None:
                    errors["invalid_date"].append(
                        {"path": relative, "field": field, "value": raw_value}
                    )

        for reference in _raw_references(frontmatter.get("sources", "")):
            if not (wiki_root / reference).is_file():
                errors["broken_source_references"].append(
                    {"path": relative, "reference": reference}
                )

        leaked = _leaked_frontmatter_items(text)
        if leaked:
            errors["frontmatter_leaked_into_body"].append(
                {"path": relative, "items": list(leaked)}
            )

        line_count = len(text.lstrip("﻿").splitlines())
        line_counts[relative] = line_count
        if line_count > hard_lines:
            errors["hard_cap_exceeded"].append(
                {"path": relative, "lines": line_count, "cap": hard_lines}
            )
        if line_count > soft_lines:
            warnings["soft_cap_exceeded"].append(
                {"path": relative, "lines": line_count, "cap": soft_lines}
            )

        placeholders = sorted(set(_find_placeholders(text)))
        if placeholders:
            warnings["template_placeholders"].append(
                {"path": relative, "matches": placeholders}
            )

        updated_raw = _unquote_scalar(frontmatter.get("updated", "").strip())
        updated_date = _parse_date(updated_raw) if updated_raw else None
        if updated_date is not None:
            age_days = (today - updated_date).days
            reliability_raw = _unquote_scalar(frontmatter.get("reliability", "").strip())
            if reliability_raw == "low" and age_days > config["staleness_days"]["low_reliability"]:
                warnings["stale_low_reliability"].append(
                    {"path": relative, "updated": updated_raw, "days": age_days}
                )
            if age_days > config["staleness_days"]["cold_page"]:
                warnings["cold_pages"].append(
                    {"path": relative, "updated": updated_raw, "days": age_days}
                )
            if (
                age_days > config["staleness_days"]["pending_review"]
                and _pending_review_has_content(text)
            ):
                warnings["stale_pending_review"].append(
                    {"path": relative, "updated": updated_raw, "days": age_days}
                )

    # Duplicate slugs (across all families).
    slug_paths = {}
    for page in pages:
        slug_paths.setdefault(page.slug, []).append(_relative(wiki_root, page.path))
    for slug in sorted(slug_paths):
        paths = sorted(slug_paths[slug])
        if len(paths) > 1:
            errors["duplicate_slugs"].append({"slug": slug, "paths": paths})

    # Broken wikilinks: every content page plus every root INDEX*.md document.
    documents_to_scan = tuple(
        sorted(
            {page.path for page in pages}.union(index_documents),
            key=lambda path: _relative(wiki_root, path),
        )
    )
    for path in documents_to_scan:
        text = texts.get(path)
        if text is None:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                text = ""
        for link in extract_wikilinks(text):
            if link.target not in target_keys:
                errors["broken_wikilinks"].append(
                    {
                        "path": _relative(wiki_root, path),
                        "line": link.line,
                        "target": link.target,
                        "raw": link.raw,
                    }
                )

    # Missing index entries: a page must be a primary bullet in INDEX.md OR its
    # own INDEX-<family-dir>.md shard.
    index_texts = {}
    for path in index_documents:
        try:
            index_texts[path] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            index_texts[path] = ""

    root_index_path = wiki_root / config["index"]["root"]
    root_entries = _primary_index_entries(index_texts.get(root_index_path, ""))
    root_targets = {entry.target for entry in root_entries}

    shard_targets_by_dir = {}
    for dirname in config["page_families"]:
        shard_path = wiki_root / f"{config['index']['shard_prefix']}{dirname}.md"
        entries = _primary_index_entries(index_texts.get(shard_path, ""))
        shard_targets_by_dir[dirname] = {entry.target for entry in entries}

    for page in pages:
        link_keys = _page_link_keys(wiki_root, page)
        present = not link_keys.isdisjoint(root_targets) or not link_keys.isdisjoint(
            shard_targets_by_dir.get(page.dirname, set())
        )
        if not present:
            errors["missing_index_entries"].append(
                {
                    "path": _relative(wiki_root, page.path),
                    "slug": page.slug,
                    "indexes": [
                        config["index"]["root"],
                        f"{config['index']['shard_prefix']}{page.dirname}.md",
                    ],
                }
            )

    # Duplicate index entries: same slug listed as a primary bullet more than
    # once across all root INDEX*.md documents.
    primary_occurrences = {}
    for index_path in index_documents:
        text = index_texts.get(index_path, "")
        for entry in _primary_index_entries(text):
            slug = entry.target.rsplit("/", 1)[-1]
            primary_occurrences.setdefault(slug, []).append(
                {"index": _relative(wiki_root, index_path), "line": entry.line}
            )
    for slug in sorted(primary_occurrences):
        occurrences = primary_occurrences[slug]
        if len(occurrences) > 1:
            errors["duplicate_index_entries"].append(
                {"slug": slug, "occurrences": occurrences}
            )

    # Orphans: no inbound wikilink from any other content page (index excluded).
    key_to_pages = {}
    for page in pages:
        for key in _page_link_keys(wiki_root, page):
            key_to_pages.setdefault(key, set()).add(page.path)

    referenced = set()
    for page in pages:
        text = texts.get(page.path, "")
        for link in extract_wikilinks(text):
            for candidate in key_to_pages.get(link.target, ()):
                if candidate != page.path:
                    referenced.add(candidate)

    for page in pages:
        if page.path not in referenced:
            warnings["orphans"].append(
                {"path": _relative(wiki_root, page.path), "slug": page.slug}
            )

    # Info block.
    inbox_dir = wiki_root / "raw" / "inbox"
    inbox_files = []
    if inbox_dir.is_dir():
        for path in inbox_dir.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                inbox_files.append(_relative(wiki_root, path))
    inbox_files.sort()

    directory_counts = {}
    for page in pages:
        directory = str(page.path.parent.relative_to(wiki_root).as_posix())
        directory_counts[directory] = directory_counts.get(directory, 0) + 1

    scale_config = config["scale_thresholds"]

    def _near(value: int, threshold: int) -> bool:
        return threshold > 0 and value >= 0.8 * threshold

    total_pages = counts["total"]
    scale = {
        "total_pages": total_pages,
        "shard_index_at_pages": scale_config["shard_index_at_pages"],
        "search_step_at_pages": scale_config["search_step_at_pages"],
        "subdivide_directory_at_pages": scale_config["subdivide_directory_at_pages"],
        "near_shard_index": _near(total_pages, scale_config["shard_index_at_pages"]),
        "near_search_step": _near(total_pages, scale_config["search_step_at_pages"]),
        "directories": [
            {
                "path": directory,
                "pages": count,
                "near_subdivide": _near(count, scale_config["subdivide_directory_at_pages"]),
            }
            for directory, count in sorted(directory_counts.items())
        ],
    }

    last_log_entry = None
    log_path = wiki_root / "LOG.md"
    if log_path.is_file():
        try:
            log_text = log_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            log_text = ""
        entry_lines = [line for line in log_text.splitlines() if line.startswith("## [")]
        if entry_lines:
            last_log_entry = entry_lines[-1][3:].strip()

    info = {
        "counts": counts,
        "reliability_distribution": reliability_distribution,
        "sensitivity_distribution": sensitivity_distribution,
        "inbox_files": inbox_files,
        "scale": scale,
        "last_log_entry": last_log_entry,
    }

    return {
        "caps": {"soft_lines": soft_lines, "hard_lines": hard_lines},
        "counts": counts,
        "pages": [
            {
                "path": _relative(wiki_root, page.path),
                "page_type": page.page_type,
                "slug": page.slug,
                "lines": line_counts.get(_relative(wiki_root, page.path), 0),
                "reliability": _unquote_scalar(frontmatters[page.path].get("reliability", "")) or None,
                "sensitivity": _unquote_scalar(frontmatters[page.path].get("sensitivity", "")) or None,
                "updated": _unquote_scalar(frontmatters[page.path].get("updated", "")) or None,
            }
            for page in pages
        ],
        "index_documents": [_relative(wiki_root, path) for path in index_documents],
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "config_path": None,
        "wiki_root": str(wiki_root),
    }


def _config_error_report(wiki_root: Path, config_path: Path, reason: str) -> dict:
    config = _default_config()
    errors = {key: [] for key in ERROR_KEYS}
    errors["config_invalid"] = [{"path": str(config_path), "reason": reason}]
    warnings = {key: [] for key in WARNING_KEYS}
    counts = {dirname: 0 for dirname in config["page_families"]}
    counts["total"] = 0
    reliability_distribution = {value: 0 for value in RELIABILITY_VALUES}
    reliability_distribution["unknown"] = 0
    sensitivity_distribution = {value: 0 for value in SENSITIVITY_VALUES}
    sensitivity_distribution["unknown"] = 0
    scale_config = config["scale_thresholds"]
    info = {
        "counts": counts,
        "reliability_distribution": reliability_distribution,
        "sensitivity_distribution": sensitivity_distribution,
        "inbox_files": [],
        "scale": {
            "total_pages": 0,
            "shard_index_at_pages": scale_config["shard_index_at_pages"],
            "search_step_at_pages": scale_config["search_step_at_pages"],
            "subdivide_directory_at_pages": scale_config["subdivide_directory_at_pages"],
            "near_shard_index": False,
            "near_search_step": False,
            "directories": [],
        },
        "last_log_entry": None,
    }
    return {
        "caps": {
            "soft_lines": config["caps"]["soft_lines"],
            "hard_lines": config["caps"]["hard_lines"],
        },
        "counts": counts,
        "pages": [],
        "index_documents": [],
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "config_path": str(config_path),
        "wiki_root": str(wiki_root),
    }


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------

def _format_finding(finding: dict) -> str:
    path = finding.get("path")
    line = finding.get("line")
    rest_keys = [key for key in finding if key not in ("path", "line")]
    rest = ", ".join(f"{key}={finding[key]!r}" for key in rest_keys)
    if path is not None and line is not None:
        prefix = f"{path}:{line}"
    elif path is not None:
        prefix = str(path)
    else:
        prefix = json.dumps(finding, ensure_ascii=False, sort_keys=True)
        return f"- {prefix}"
    if rest:
        return f"- {prefix} — {rest}"
    return f"- {prefix}"


def format_text(report: dict, today: date) -> str:
    counts = report["counts"]
    total = counts.get("total", 0)
    family_names = [key for key in counts if key != "total"]
    family_phrase = ", ".join(f"{counts[name]} {name}" for name in family_names)
    error_total = sum(len(items) for items in report["errors"].values())
    warning_total = sum(len(items) for items in report["warnings"].values())
    inbox_count = len(report["info"].get("inbox_files", []))

    lines = [f"# Wiki lint — {today.isoformat()}", "", "## Summary"]
    lines.append(f"{total} pages ({family_phrase}).")
    lines.append(f"{error_total} errors, {warning_total} warnings.")
    lines.append(f"{inbox_count} file{'s' if inbox_count != 1 else ''} in raw/inbox.")
    lines.append("")

    lines.append("## Errors")
    if error_total == 0:
        lines.append("No errors.")
    else:
        for key in ERROR_KEYS:
            findings = report["errors"].get(key, [])
            if not findings:
                continue
            lines.append(f"### {key}")
            for finding in findings:
                lines.append(_format_finding(finding))
            lines.append("")
    lines.append("")

    lines.append("## Warnings")
    if warning_total == 0:
        lines.append("No warnings.")
    else:
        for key in WARNING_KEYS:
            findings = report["warnings"].get(key, [])
            if not findings:
                continue
            lines.append(f"### {key}")
            for finding in findings:
                lines.append(_format_finding(finding))
            lines.append("")
    lines.append("")

    lines.append("## Info")
    info = report["info"]
    lines.append(f"- Counts: {json.dumps(info['counts'], sort_keys=True)}")
    lines.append(
        f"- Reliability distribution: {json.dumps(info['reliability_distribution'], sort_keys=True)}"
    )
    lines.append(
        f"- Sensitivity distribution: {json.dumps(info['sensitivity_distribution'], sort_keys=True)}"
    )
    lines.append(f"- Inbox files: {inbox_count}")
    scale = info["scale"]
    lines.append(
        "- Scale: "
        f"{scale['total_pages']} total pages "
        f"(shard index at {scale['shard_index_at_pages']}, "
        f"search step at {scale['search_step_at_pages']})"
    )
    last_log_entry = info.get("last_log_entry")
    lines.append(f"- Last log entry: {last_log_entry if last_log_entry else 'none'}")

    # Collapse consecutive blank lines produced by the section loops above.
    collapsed = []
    previous_blank = False
    for line in lines:
        if line == "" and previous_blank:
            continue
        collapsed.append(line)
        previous_blank = line == ""
    return "\n".join(collapsed).rstrip("\n") + "\n"


def format_brief(report: dict) -> str:
    counts = report["counts"]
    total = counts.get("total", 0)
    family_names = [key for key in counts if key != "total"]
    family_phrase = ", ".join(f"{counts[name]} {name}" for name in family_names)
    error_total = sum(len(items) for items in report["errors"].values())
    warning_total = sum(len(items) for items in report["warnings"].values())
    inbox_count = len(report["info"].get("inbox_files", []))

    lines = [
        f"Wiki: {total} pages ({family_phrase}) · {error_total} errors · "
        f"{warning_total} warnings · {inbox_count} file"
        f"{'s' if inbox_count != 1 else ''} in raw/inbox"
    ]

    last_log_entry = report["info"].get("last_log_entry")
    lines.append(f"Last log: {last_log_entry if last_log_entry else 'none'}")

    if warning_total:
        parts = [
            f"{key} {len(report['warnings'][key])}"
            for key in WARNING_KEYS
            if report["warnings"].get(key)
        ]
        lines.append("Warnings: " + ", ".join(parts))

    if error_total:
        parts = [
            f"{key} {len(report['errors'][key])}"
            for key in ERROR_KEYS
            if report["errors"].get(key)
        ]
        lines.append("Errors: " + ", ".join(parts))

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _build_arg_parser() -> _ArgParser:
    parser = _ArgParser(description=__doc__)
    parser.add_argument("--wiki-root", default="wiki")
    parser.add_argument("--config", default=None)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--brief", action="store_true")
    parser.add_argument("--today", default=None)
    return parser


def _emit(report: dict, args, today: date) -> None:
    if args.brief:
        sys.stdout.write(format_brief(report))
    elif args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        sys.stdout.write(format_text(report, today))


def main(argv=None) -> int:
    parser = _build_arg_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_signal:
        code = exit_signal.code
        return code if isinstance(code, int) else 1

    today = date.today()
    if args.today:
        try:
            today = datetime.strptime(args.today, "%Y-%m-%d").date()
        except ValueError:
            print(f"invalid --today value: {args.today!r} (expected YYYY-MM-DD)", file=sys.stderr)
            return 1

    wiki_root = Path(args.wiki_root)
    if not wiki_root.is_dir():
        print(f"wiki root does not exist or is not a directory: {wiki_root}", file=sys.stderr)
        return 1

    config_path = resolve_config_path(args.config, wiki_root)
    try:
        config = load_config(args.config, wiki_root)
    except ConfigError as error:
        report = _config_error_report(wiki_root, config_path, str(error))
        _emit(report, args, today)
        return 1

    try:
        report = build_report(wiki_root, config, today)
    except OSError as error:
        print(f"could not scan wiki: {error}", file=sys.stderr)
        return 1

    report["config_path"] = str(config_path)
    _emit(report, args, today)

    has_errors = any(report["errors"].values())
    return 2 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
