# LLM Wiki Template — Implementation Plan

Spec: `docs/superpowers/specs/2026-09-10-llm-wiki-template-design.md`

Execution model: orchestrator (Fable) writes the contract files and all skill/schema prose; scripts, tests and docs are delegated to Sonnet subagents in parallel; a final review and end-to-end validation run before publishing.

## Phase A — foundation (orchestrator)

- [x] Spec written and self-reviewed.
- [ ] `wiki.config.json`, `wiki/CLAUDE.md`, `wiki/_templates/*.md`, `wiki/INDEX.md`, `wiki/LOG.md`, `wiki/README.md`
- [ ] Root `CLAUDE.md`, `AGENTS.md`, `.gitignore`, `.editorconfig`, `LICENSE`, `CUSTOMIZATIONS.md`
- [ ] Tutorial source `wiki/raw/inbox/2026-09-10-welcome-to-your-llm-wiki.md`
- [ ] `.claude/settings.json`, `.claude/rules/raw-immutability.md`, `.claude/agents/wiki-scout.md`
- [ ] Initial commit.

## Phase B — parallel build (subagents, Sonnet)

Each task: read the spec section, port from the reference implementation where given, write tests first, keep Python 3.9+ stdlib only, commit on the shared branch with a scoped message.

- [ ] B1 `scripts/wiki_lint.py` + `tests/test_wiki_lint.py` (reference: `gm/.claude/skills/wiki-lint/scripts/page_inventory.py`)
- [ ] B2 `scripts/privacy_preflight.py`, `scripts/validate_privacy_ledger.py` + tests (reference: `gm/.claude/skills/wiki-ingest/scripts/*.py` and their tests)
- [ ] B3 `scripts/hooks/pre-commit`, `scripts/hooks/guard_write.py`, `scripts/hooks/session_start.py`, `scripts/new_page.py`, `scripts/wiki_search.py`, `scripts/bootstrap.py` + tests
- [ ] (orchestrator, concurrently) all nine `SKILL.md` files + `references/sensitivity-taxonomy.md` + `references/adapters/jamie.md`

## Phase C — docs and contract tests (subagents)

- [ ] C1 `README.md`, `docs/onboarding.md`, `docs/privacy.md`, `docs/skills.md`, `docs/customizing.md`, `docs/faq.md`, `docs/design.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`
- [ ] C2 `tests/test_skill_contracts.py`, `tests/test_template_integrity.py`, `.github/workflows/checks.yml`, `.github/workflows/inbox-drainer.yml`

## Phase D — validation and publish

- [ ] Full test suite green; lint zero errors; hooks exercised in a temp clone.
- [ ] End-to-end: fresh subagent copies the repo to a temp dir, runs `/wiki-ingest` on the tutorial source and `/wiki-lint`; result passes lint.
- [ ] Reviewer pass (spec compliance, leakage denylist, docs accuracy).
- [ ] History scan; `gh repo create georgemavchun/llm-wiki-template --private --source . --push`; enable template flag.
- [ ] Report to owner with decisions to confirm (visibility, license).
