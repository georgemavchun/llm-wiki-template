---
name: wiki-share
description: Use when content from this personal wiki should be exported to a team or project wiki configured in `wiki.config.json` — "share this with the team wiki", "sync the team wiki", "push what's shareable", "drain the share backlog", "what could go to the project wiki" — or to preview such an export with a dry run. Inactive when no share destinations are configured.
---

# Wiki Share

Batch, owner-gated export of sanitized extracts from this wiki into one or more team wikis. The sensitivity taxonomy in [references/sensitivity-taxonomy.md](references/sensitivity-taxonomy.md) decides what may travel and how it must be transformed. Nothing is written to a destination without an explicit confirmation in the same run.

## Preconditions

- `wiki.config.json → share.destinations` has at least one entry. If it is empty, say so and stop; offer `docs/customizing.md` for how to add one.
- Read `wiki/CLAUDE.md`, `wiki/LOG.md`, `wiki/INDEX.md`, the taxonomy, and each destination's own schema (`<path>/CLAUDE.md` or `README.md`) for naming, language and frontmatter conventions.

## Modes

- **Dry run** (`--dry-run`, "preview", "what would go"): everything except writing. Default on a first run.
- **Backlog drain**: entries in `LOG.md` since the last `## [date] share |` marker that have a `Classification:` line but no `share-status:` for the destination.
- **Fresh classify**: entries referencing a destination's topics that have no `Classification:` yet. Classify, then drain.

## Workflow

### 1. Collect candidates from `LOG.md`

Find the last `## [YYYY-MM-DD] share |` marker (none means the whole log). For each newer entry extract date, operation, created pages, `Classification:` counts and any `share-status: written-<dest> | skipped-<dest>`. Exclude maintenance entries (lint, evolve, redaction, bootstrap), entries already written or skipped for the destination, and entries whose classification is only `quarantine` and `personal`.

For crystallize and synthesis entries, do a structural check on the page: wikilinks to identifiable people, figures about pay or compensation, blame or evaluation, legal or regulatory exposure. All clear → candidate; otherwise classify properly or skip.

### 2. Classify what is unclassified

Block by block against the taxonomy: class, action, confidence, review state, proposal bucket, reason codes, destinations. Keep a temporary ledger outside the repository (see `.claude/skills/wiki-ingest/references/transcript-ledger.md`) and validate it with `scripts/validate_privacy_ledger.py`.

### 3. Batch review

Present one scannable review, grouped by destination then by risk:

- **Safe batch** — `shareable`, `confidence: high`, `approved`: a table of `#`, date, source, one-line summary. Ask: push all? (`yes`, `<destination>-only`, `no`).
- **Individual review** — `restricted` and every `borderline-review` item regardless of class: `#`, date, source, summary, class, transformation (`generalize | anonymize | aggregate`), risk, proposed confidentiality at the destination. Ask for the numbers to include.
- **Excluded** — counts by class and reason category only. No excerpts.

### 4. Produce extracts

For each approved item: keep `shareable` blocks; apply the assigned transformation to approved `restricted` blocks; drop `personal` and `quarantine` blocks, keeping a neutral abstraction only when it preserves a decision, action, rationale or lesson; strip quasi-identifiers (rare role, small team, exact dates, client, location, verbatim quotes); translate to the destination language if it differs. Participant names appear only when each identity is independently approved and ordinary project coordination; otherwise use role labels or omit.

Each extract starts with:

```markdown
source-date: YYYY-MM-DD
source-type: <transcript|document|synthesis>-filtered
destination: <name>
filtered: true
full-source: personal-wiki
taxonomy-version: <from wiki.config.json>
confidentiality: internal | restricted

# <Title> — filtered extract

> Sensitivity-filtered extract. The full source, including personal and restricted discussion, stays in the author's personal wiki. This file contains only material approved for this destination at the stated confidentiality level.
```

Batch same-week, same-destination items into one digest when that does not mix confidentiality levels or lose traceability.

### 5. Confirm, then write

List every file to be created with its destination path (`<path>/<raw_dir>/<filename>` in the destination's filename style). Ask: write these and run the destination's ingest? Only on an explicit yes:

1. Write the extract files.
2. Run the destination wiki's own ingest procedure on them (its skill, its schema), setting `confidentiality: restricted` when any `restricted` block is included, and never creating entity pages for people whose only mentions were `personal`.
3. In this wiki's `LOG.md`, add `share-status: written-<dest>` or `skipped-<dest>` inside each affected entry (this is the one permitted edit to earlier log entries), and append the marker:

```markdown
## [YYYY-MM-DD] share | <dest>: <n> items (<s> safe + <r> restricted)

Candidates: <n> · Already shared: <n> · Personal-only: <n> · Excluded by owner: <n> · Dry run: yes | no
```

### 6. Report

Scan counts, classification counts, review decisions, files written per destination, exclusions. Never reproduce excluded content.

## Hard boundaries

- No write to any destination without the per-run confirmation in step 5, even for the safe batch.
- `quarantine` and `personal` content never leaves this wiki. Owner approval cannot override third-party data-subject risk, legal privilege, financial-crime tipping-off risk, active secrets or an explicit off-record instruction.
- Generalize rather than delete when a safe abstraction keeps value; delete when none does.
- Running twice with no new log entries is a no-op and says so.
