# Agent Guide

This repository is a personal LLM wiki built from `llm-wiki-template`. The knowledge base lives in `wiki/`; everything else is tooling that keeps it healthy and private.

@wiki/CLAUDE.md

## Operating rules

- The wiki schema above is binding. When a skill and the schema disagree, the schema wins.
- Every wiki operation is a skill under `.claude/skills/wiki-*/`. Invoke the matching skill instead of improvising: `wiki-ingest`, `wiki-ingest-light`, `wiki-ingest-meetings`, `wiki-crystallize`, `wiki-query`, `wiki-lint`, `wiki-evolve`, `wiki-share`, `wiki-setup`.
- Nothing enters `wiki/raw/` without `python3 scripts/privacy_preflight.py`. A `PreToolUse` hook and a git pre-commit hook enforce this; do not work around them.
- Prefer deterministic scripts over judgment for anything mechanically checkable: `scripts/wiki_lint.py`, `scripts/wiki_search.py`, `scripts/new_page.py`.
- Durable knowledge belongs in the wiki, not in agent memory. If asked to remember something, file it with `wiki-crystallize` and say where it went.

## Commands

```bash
python3 scripts/wiki_lint.py --wiki-root wiki            # integrity report (exit 2 on errors)
python3 scripts/wiki_search.py "query terms"             # BM25 search over wiki pages
python3 scripts/privacy_preflight.py <file>              # scan before anything enters wiki/raw/
python3 scripts/new_page.py entities <slug> --title "…"  # scaffold a page from wiki/_templates/
python3 -m unittest discover -s tests -v                 # tooling tests
```

## Git

- Small, semantic commits: `ingest: <source>`, `crystallize: <topic>`, `lint: <date>`, `schema: <change>`.
- Never commit `.staging/`. Never force-push. Do not rewrite history to remove sensitive data without the owner; follow `docs/privacy.md`.
- Personal permission overrides go in `.claude/settings.local.json` (gitignored), not in the shared `settings.json`.
