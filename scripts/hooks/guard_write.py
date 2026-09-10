#!/usr/bin/env python3
"""Claude Code PreToolUse hook: protect ``wiki/raw/`` and block secrets.

Reads a PreToolUse JSON payload from stdin for the ``Write``, ``Edit`` and
``MultiEdit`` tools. Two rules are enforced:

1. Any write whose target path resolves under ``<wiki_root>/raw/`` (at any
   depth, including ``inbox/``) is refused — raw sources are add-only and
   must be moved into place after a manual privacy-preflight scan, never
   created or edited by a file tool.
2. Any write whose new content trips ``privacy_preflight.scan_text`` is
   refused. The category and reason code are reported; the matched value
   itself is never printed anywhere.

Exit codes follow the Claude Code hook contract: ``0`` allows the tool call,
``2`` blocks it (the stderr message is shown to the model). Any other tool
name passes through with exit ``0``. By design, any internal error in this
hook (malformed stdin JSON, a missing field, a broken import, ...) is
**non-blocking**: it is reported on stderr and the hook exits ``1``, which
Claude Code treats as a hook failure rather than a block, so a bug in this
script can never lock the user out of editing their own wiki.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WRITE_TOOLS = ("Write", "Edit", "MultiEdit")
MAX_FINDINGS_REPORTED = 10


def _project_dir(payload: dict) -> Path:
    candidate = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    return Path(candidate)


def _resolve_target(file_path: str, project_dir: Path) -> Path:
    candidate = Path(file_path)
    if candidate.is_absolute():
        return candidate
    return project_dir / candidate


def _load_wiki_root(project_dir: Path) -> str:
    config_path = project_dir / "wiki.config.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        root = data.get("wiki_root")
        if isinstance(root, str) and root:
            return root
    except Exception:
        pass
    return "wiki"


def _display_path(path: Path, project_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_dir.resolve()))
    except Exception:
        return str(path)


def _collect_new_text(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Write":
        return str(tool_input.get("content", ""))
    if tool_name == "Edit":
        return str(tool_input.get("new_string", ""))
    if tool_name == "MultiEdit":
        pieces = []
        for edit in tool_input.get("edits") or []:
            pieces.append(str(edit.get("new_string", "")))
        return "\n".join(pieces)
    return ""


def run(payload: dict) -> int:
    tool_name = payload.get("tool_name")
    if tool_name not in WRITE_TOOLS:
        return 0

    tool_input = payload.get("tool_input") or {}
    project_dir = _project_dir(payload)
    file_path_raw = tool_input["file_path"]
    target = _resolve_target(file_path_raw, project_dir)

    wiki_root = _load_wiki_root(project_dir)
    raw_dir = (project_dir / wiki_root / "raw").resolve()

    try:
        resolved_target = target.resolve()
    except Exception:
        resolved_target = target

    is_under_raw = False
    try:
        is_under_raw = resolved_target.is_relative_to(raw_dir)
    except AttributeError:  # pragma: no cover - Python < 3.9 fallback
        try:
            resolved_target.relative_to(raw_dir)
            is_under_raw = True
        except ValueError:
            is_under_raw = False

    if is_under_raw:
        rel = _display_path(resolved_target, project_dir)
        print(
            "guard_write: {rel} is under {root}/raw/, which is add-only. "
            "Stage the file in .staging/, run python3 scripts/privacy_preflight.py "
            "on it, then mv it into {root}/raw/.".format(rel=rel, root=wiki_root),
            file=sys.stderr,
        )
        return 2

    new_text = _collect_new_text(tool_name, tool_input)

    sys.path.insert(0, str(project_dir / "scripts"))
    from privacy_preflight import scan_text  # noqa: E402  (deliberate late import)

    findings = scan_text(new_text)
    if findings:
        for finding in findings[:MAX_FINDINGS_REPORTED]:
            print(
                "guard_write: blocked — {category}/{reason} at new-content line {line} "
                "(value not shown). Remove or redact it before writing.".format(
                    category=finding.category, reason=finding.reason_code, line=finding.line
                ),
                file=sys.stderr,
            )
        return 2

    return 0


def main() -> int:
    try:
        raw_stdin = sys.stdin.read()
        payload = json.loads(raw_stdin) if raw_stdin.strip() else {}
        return run(payload)
    except Exception as exc:  # noqa: BLE001 - fail open by design, see module docstring
        print(f"guard_write: error ({type(exc).__name__}) — allowing the write", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
