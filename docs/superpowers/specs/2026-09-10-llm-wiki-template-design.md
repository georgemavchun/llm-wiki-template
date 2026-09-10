# LLM Wiki Template — Design Spec

Date: 2026-09-10
Status: approved for implementation (autonomous session; decisions recorded here for owner review)
Owner: George Mavchun

## 1. Purpose

A fork-ready GitHub template repository for a **personal, git-tracked, markdown knowledge base maintained by a coding agent** (Claude Code first; Codex/Cursor-compatible), following Andrej Karpathy's "LLM Wiki" pattern (gist `442a6bf555914893e9891c11519de94f`, 2026-04-04).

Colleagues create their own copy with GitHub's **"Use this template"** button, run a five-minute bootstrap, and get:

- a three-layer wiki (raw sources → agent-maintained pages → schema),
- a coherent set of agent skills (ingest, ingest-light, ingest-meetings, crystallize, query, lint, evolve, share, setup),
- deterministic guardrails for privacy and integrity (secret/PII scanner, sensitivity ledger, git hooks, Claude Code hooks, CI),
- onboarding and reference documentation.

## 2. Inputs the design combines

| Source | What we take | What we leave |
|---|---|---|
| Karpathy gist | raw/wiki/schema layers; ingest/query/lint; `INDEX.md` + `LOG.md`; Obsidian as viewer; scale notes | abstractness — we instantiate concrete conventions |
| Owner's personal wiki | schema shape (frontmatter, reliability, Pending Review, page caps, surgical edits, scale thresholds), privacy preflight scanner, classification ledger + validator, meeting-recorder (Jamie) batch ingest, project-sync taxonomy, deterministic lint inventory | person/company-specific paths, names, reflections/recipes page types, multi-language rules as defaults |
| Corporate wiki (employer) | `ingest-light`, `evolve` (TRIZ meta-review), lazy page creation, "editorial collaborator, not sycophant" preamble, auto-maintenance nudges, decision/incident templates idea | domain split (product/engineering/business), sales zone, spaces-in-filenames |
| Second corporate wiki (side venture) | `confidentiality` frontmatter, explicit "never paste" list, auto-evolve triggers (activity/calendar/incident), ingest-light without source page | governed pointers, roadmap tooling, tactical board |
| Online research (2026-09) | template-not-fork distribution; stdlib scanner + optional gitleaks; record-category-not-content redaction ledgers; OWASP LLM01 indirect prompt injection and Anthropic mitigations; `.claude/rules` with `paths:`; PreToolUse hooks for hard rules; `CUSTOMIZATIONS.md` delta file (obsidian-second-brain); "as of" dating for facts; deterministic-lint vs LLM-judgment split (praneybehl); transaction-style audit trail (claude-obsidian); honest "everything under the wiki root is sent to the model provider" statement (vanillaflava) | typed graph edges, vector search, MCP server, hosted app, multi-platform build pipeline — premature for a personal template |

## 3. Decisions made autonomously (owner may override)

1. **Repo name** `llm-wiki-template`, created **private** in `georgemavchun`, with the *template repository* flag enabled. Flip to public when ready; private template repos are usable by collaborators only.
2. **License** MIT (permissive, template-friendly). Change if the company prefers otherwise.
3. **Layout** wiki content lives under `wiki/` (Obsidian vault = `wiki/`), tooling at repo root. Matches George's personal repo and keeps docs/scripts out of the vault.
4. **Python 3.9+ standard library only** for every script. No pip installs. `gitleaks` is an optional extra layer, auto-detected.
5. **Page types** shipped: `sources`, `entities`, `concepts`, `synthesis`. Others (reflections, recipes, decisions, projects) are documented as extensions, not shipped.
6. **Language policy default** English for structure and wiki prose; sources kept verbatim in their original language. Owner may switch to "preserve source language in pages" in the schema.
7. **Sensitivity vocabulary** four classes: `quarantine` (never stored), `personal` (never leaves this wiki), `restricted` (may go to a team wiki with per-item approval), `shareable` (may go to a team wiki after normal review). Page-level `sensitivity:` frontmatter uses `personal | restricted | shareable | public`, default `personal`.
8. **Team-wiki destinations** are configuration (`wiki.config.json → share.destinations`), empty by default. The share skill is a no-op until the owner configures one.
9. **Meeting-recorder ingest** ships adapter-agnostic with one reference adapter (Jamie MCP). Other recorders are documented as a 20-line adapter file.
10. **Classification ledger** required for transcripts, optional for other sources (config `privacy.ledger_required_for: ["transcript"]`). Deterministic preflight scan is mandatory for every source entering `wiki/raw/`.
11. **Inbox drainer CI workflow** ships disabled (manual dispatch only) with an explicit data-flow warning.
12. **Distribution** standalone `.claude/skills/` (primary). Plugin packaging is a documented roadmap item, not shipped.

## 4. Architecture

### 4.1 Three layers

```
wiki/raw/            immutable sources (add-only; inbox/ is the drop zone)
wiki/{sources,entities,concepts,synthesis}/   agent-owned pages
wiki/CLAUDE.md       schema — the human-owned contract
```

Supporting files: `wiki/INDEX.md` (catalog), `wiki/LOG.md` (append-only audit trail), `wiki/_templates/*.md` (page scaffolds), `wiki.config.json` (machine-readable settings).

### 4.2 Repository tree

```
llm-wiki-template/
├── README.md  LICENSE  CHANGELOG.md  CONTRIBUTING.md  SECURITY.md  CUSTOMIZATIONS.md
├── CLAUDE.md                # short repo guide; imports @wiki/CLAUDE.md
├── AGENTS.md                # pointer for non-Claude agents
├── wiki.config.json         # page families, caps, privacy settings, share destinations
├── .gitignore  .editorconfig
├── .claude/
│   ├── settings.json        # permissions + hooks (shared)
│   ├── rules/raw-immutability.md     # paths: wiki/raw/**
│   ├── agents/wiki-scout.md          # haiku, read-only candidate finder
│   └── skills/
│       ├── wiki-setup/         wiki-ingest/        wiki-ingest-light/
│       ├── wiki-ingest-meetings/ (references/adapters/jamie.md)
│       ├── wiki-crystallize/   wiki-query/         wiki-lint/
│       ├── wiki-evolve/        wiki-share/ (references/sensitivity-taxonomy.md)
├── scripts/
│   ├── wiki_lint.py  wiki_search.py  new_page.py  bootstrap.py
│   ├── privacy_preflight.py  validate_privacy_ledger.py
│   └── hooks/pre-commit  hooks/guard_write.py  hooks/session_start.py
├── tests/                   # unittest, stdlib only
├── docs/                    # onboarding, privacy, skills, customizing, design, faq
├── .github/workflows/checks.yml  inbox-drainer.yml
└── wiki/
    ├── CLAUDE.md  README.md  INDEX.md  LOG.md
    ├── _templates/{source,entity,concept,synthesis}.md
    ├── raw/inbox/2026-09-10-welcome-to-your-llm-wiki.md   # tutorial source
    └── sources/ entities/ concepts/ synthesis/   (.gitkeep)
```

`.staging/` (gitignored, created by bootstrap) is where pasted or downloaded content waits for the privacy preflight before it may enter `wiki/raw/`.

### 4.3 Configuration (`wiki.config.json`)

```json
{
  "schema_version": 1,
  "wiki_root": "wiki",
  "page_families": {"sources": "source", "entities": "entity", "concepts": "concept", "synthesis": "synthesis"},
  "caps": {"soft_lines": 400, "hard_lines": 800},
  "index": {"root": "INDEX.md", "shard_prefix": "INDEX-"},
  "privacy": {"ledger_required_for": ["transcript"], "taxonomy_version": "2026-09-10"},
  "share": {"destinations": {}}
}
```

A destination entry looks like `"team": {"path": "../team-wiki", "raw_dir": "raw/inbox", "language": "en", "filename_style": "kebab"}`.

Scripts fall back to these defaults when the file is absent. Lint validates the file.

### 4.4 Frontmatter contract

```yaml
---
title: "<human title>"
page_type: source | entity | concept | synthesis
reliability: high | medium | low
sensitivity: personal | restricted | shareable | public
sources: ["raw/<file>", "sources/<slug>.md", "conversation:YYYY-MM-DD"]
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [a, b]
---
```

Rules carried over: filename slug kebab-case ASCII; `page_type` matches directory; `reliability: high` needs two independent sources; unverified claims go under `## Pending Review`; soft cap 400 lines, hard cap 800; surgical edits only; facts dated "as of" when time-bound.

### 4.5 Skills

| Skill | Trigger | Writes | Deterministic steps |
|---|---|---|---|
| `wiki-setup` | first run, "set up my wiki" | placeholders in CLAUDE/README, hooks install | `scripts/bootstrap.py` |
| `wiki-ingest` | "ingest X", inbox files, URLs, transcripts | raw placement, source page, entity/concept edits, INDEX, LOG | `privacy_preflight.py`; ledger validation for transcripts; `wiki_lint.py --brief` at the end |
| `wiki-ingest-light` | fragments, snippets, quick notes | raw fragment, surgical edits, LOG (no source page) | `privacy_preflight.py` |
| `wiki-ingest-meetings` | "pull new meetings", recorder sync | staging + tags; delegates writing to `wiki-ingest` | adapter-specific discovery; idempotence via recorder tags |
| `wiki-crystallize` | "crystallize this", end of session | concept/synthesis pages, INDEX, LOG | — (confirm placement first) |
| `wiki-query` | "what does the wiki say about…" | optional synthesis page | `wiki_search.py` when index is large; `wiki-scout` subagent optional |
| `wiki-lint` | "lint the wiki" | one LOG line | `wiki_lint.py` errors/warnings/info + LLM checks (contradictions, weak links) |
| `wiki-evolve` | every ~20 log entries / "evolve" | proposals; schema edits only with approval | metrics from `wiki_lint.py --format json` |
| `wiki-share` | "share X to the team wiki", "sync team wiki" | sanitized extracts into configured destinations, LOG status | taxonomy + ledger; dry-run; per-write confirmation |

Skill authoring rules: portable frontmatter only (`name`, `description`), descriptions state triggers, bodies under ~250 lines, heavy references in `references/`, scripts referenced by path, exit codes documented.

### 4.6 Privacy and integrity model

Threats addressed: (1) secrets/PII pasted into a git-tracked repo; (2) personal or third-party sensitive content leaking into shared/team wikis; (3) indirect prompt injection from ingested documents; (4) silent corruption of source truth; (5) forks inheriting someone else's data.

Controls, layered:

1. **Quarantine tier**: a "never enters the repo" list in the schema (credentials, government IDs, card data, health, compensation, legal privilege, explicit off-record). `privacy_preflight.py` detects the deterministic subset; exit `2` blocks; output never echoes matched values.
2. **Classification ledger** (transcripts): content-free JSON bound to the source SHA-256 and line count; ordered, gap-free block coverage; validated by `validate_privacy_ledger.py` (exit `3` = quarantine present).
3. **Redaction record**: redactions log category, locator, authoriser, and affected files in `LOG.md`, never the content.
4. **Raw immutability**: `.claude/settings.json` denies `Edit(./wiki/raw/**)`; `guard_write.py` (PreToolUse) blocks Write/Edit on existing raw files and blocks any Write/Edit whose content trips the scanner; git `pre-commit` refuses modifications or deletions under `wiki/raw/` unless `WIKI_ALLOW_RAW_CHANGE=1` (documented redaction override), refuses anything under `.staging/`, and scans staged wiki files; CI repeats the raw add-only and scan checks.
5. **Untrusted sources**: schema and ingest skill state that source text is data; instructions inside sources are never followed, links never opened, destinations never broadened; suspected injection is classified `quarantine` by the scanner.
6. **Template distribution**: README instructs "Use this template", explains why forking is unsafe, and the template's own history is scanned before publishing.
7. **Honest disclosure**: docs state that everything the agent reads under the repo goes to the model provider, and that the wiki root must not sit next to unrelated secrets.

### 4.7 Claude Code integration

- `.claude/settings.json`: allow `python3 scripts/*`, `git status/diff/log/add/commit`; ask for `rm`, force pushes, resets; deny `Edit(./wiki/raw/**)` and `Read(./.staging/**)`? — no: the agent must read staged files to classify them. Deny only `Edit` on raw.
- Hooks: `PreToolUse` (`Edit|Write`) → `guard_write.py`; `SessionStart` → `session_start.py` prints a five-line wiki status (page counts, inbox count, lint error count, last log entry).
- `.claude/rules/raw-immutability.md` with `paths: ["wiki/raw/**"]`.
- `.claude/agents/wiki-scout.md`: `model: haiku`, tools `Read, Grep, Glob, Bash(python3 scripts/wiki_search.py *)`, returns candidate page list with one-line reasons.

### 4.8 CI

- `checks.yml` (push, PR): `python3 -m unittest discover tests`, `python3 scripts/wiki_lint.py --wiki-root wiki` (errors fail), raw add-only diff check, `privacy_preflight.py` over changed files under `wiki/`.
- `inbox-drainer.yml`: `workflow_dispatch` only; commented cron; uses `anthropics/claude-code-action@v1` with `ANTHROPIC_API_KEY`; opens a PR. Header warning about data flow.

### 4.9 Onboarding

`docs/onboarding.md` walks: prerequisites → "Use this template" → clone → `python3 scripts/bootstrap.py` (or `/wiki-setup`) → open Claude Code → `ingest the inbox` on the tutorial source → `what does the wiki say about the LLM wiki pattern` → `lint the wiki` → commit. Includes a troubleshooting table and a "what to never paste" card.

## 5. Error handling

- Scripts exit `0` clean, `2` findings/blocked, `1` could not run; `validate_privacy_ledger.py` adds `3` = valid but quarantined. Skills fail closed on `1`.
- Hooks: `guard_write.py` exits `2` with a one-line stderr reason; never prints matched values. Hook failure (exception) exits `1` and is non-blocking, logged to stderr, so a broken hook cannot lock the user out.
- Bootstrap is idempotent; re-running reports "already done" per step.

## 6. Testing

- Unit tests for every script (fixtures in `tests/fixtures/`).
- Contract tests: every `SKILL.md` has valid frontmatter, name equals directory, referenced scripts/paths exist, no owner-specific strings (denylist), body under size cap.
- Template integrity: shipped wiki passes lint with zero errors; config parses; every relative link in docs resolves; templates carry required frontmatter keys.
- Hook tests run the shell hook inside a temporary git repository.
- End-to-end validation before publish: a fresh subagent in a temporary copy runs `wiki-ingest` on the tutorial source, then `wiki-lint`, and the result passes lint with zero errors.

## 7. Out of scope (documented as roadmap)

Plugin/marketplace packaging; typed graph edges; vector search; hosted UI; multi-platform skill compilation; automatic log rotation; per-page content hashes.
