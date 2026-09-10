#!/usr/bin/env python3
"""Claude Code SessionStart hook: inject a short wiki status brief.

Reads and discards stdin (the SessionStart payload — ``session_id``,
``hook_event_name``, ``source`` — carries nothing this hook needs). Prints a
short status brief built from ``wiki_lint`` plus one fixed reminder line;
that stdout is injected as context for the new session.

This hook must never block a session from starting: any failure while
building the lint brief (missing ``wiki_lint`` module, unreadable config, a
lint crash, ...) is swallowed, noted on stderr, and the fixed reminder line
is still printed. The hook always exits ``0``.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

REMINDER = "Read wiki/CLAUDE.md before editing the wiki; use the wiki-* skills for every operation."


def _project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def build_brief(project_dir: Path) -> str:
    sys.path.insert(0, str(project_dir / "scripts"))
    import wiki_lint  # type: ignore  # may not exist yet; caller handles ImportError

    config_path = project_dir / "wiki.config.json"
    config = wiki_lint.load_config(config_path if config_path.exists() else None, "wiki")
    wiki_root_name = config.get("wiki_root", "wiki") if isinstance(config, dict) else "wiki"
    wiki_root = project_dir / wiki_root_name
    report = wiki_lint.build_report(wiki_root, config, date.today())
    return wiki_lint.format_brief(report)


def main() -> int:
    try:
        sys.stdin.read()
    except Exception:
        pass

    output_lines = []
    try:
        brief = build_brief(_project_dir())
        if brief:
            output_lines.append(brief)
    except Exception as exc:
        print(f"session_start: skipped wiki status brief ({type(exc).__name__})", file=sys.stderr)

    output_lines.append(REMINDER)
    print("\n".join(output_lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
