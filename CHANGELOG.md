# Changelog

All notable changes to the template. Copies record their own deviations in `CUSTOMIZATIONS.md`.

## Unreleased

## 0.1.0 — 2026-09-10

First release.

- Three-layer wiki layout under `wiki/` with schema (`wiki/CLAUDE.md`), templates, index and log.
- Skills: `wiki-setup`, `wiki-ingest`, `wiki-ingest-light`, `wiki-ingest-meetings` (Jamie adapter), `wiki-crystallize`, `wiki-query`, `wiki-lint`, `wiki-evolve`, `wiki-share`.
- Deterministic tooling (Python 3.9+, stdlib only): `wiki_lint.py`, `wiki_search.py`, `new_page.py`, `bootstrap.py`, `privacy_preflight.py`, `validate_privacy_ledger.py`.
- Guardrails: Claude Code `PreToolUse` write guard, `SessionStart` status, permission deny on `wiki/raw/`, git pre-commit hook (raw add-only, staging never committed, privacy scan, optional gitleaks), CI checks.
- Sensitivity taxonomy with four classes (`quarantine`, `personal`, `restricted`, `shareable`) and a content-free classification ledger for transcripts.
- Documentation: README, onboarding, privacy, skills, customizing, design, FAQ.
