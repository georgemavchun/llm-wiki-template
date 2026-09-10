---
name: wiki-lint
description: Use when the user asks to lint, audit, check or health-check the wiki ("lint the wiki", "wiki status", "is the wiki healthy", "check for broken links"), before a large restructuring, after a batch of ingests, or when the maintenance nudge in `LOG.md` suggests it. Reports errors, warnings and info; fixes nothing.
---

# Wiki Lint

Health-check the wiki and report. Lint is read-only: it never fixes, deletes, moves or rewrites. Acting on findings is a separate conversation.

## Workflow

### 1. Deterministic scan

```bash
python3 scripts/wiki_lint.py --wiki-root wiki --format text
```

Exit `0` no errors, `2` errors present, `1` the scan could not run (fix that first; the report is incomplete without it). Add `--format json` when you need the structured data.

The script checks everything mechanically checkable — required frontmatter and enum values, page type versus directory, hard and soft caps, broken wikilinks, duplicate slugs, dangling raw references, index membership and duplicates, leaked frontmatter, template placeholders, orphans, stale low-reliability pages, stale Pending Review sections, cold pages, inbox backlog, page counts, reliability and sensitivity distributions, and scale-threshold proximity.

### 2. Judgment checks

Only the LLM can do these. Keep them proportionate to wiki size; on a large wiki, sample the pages touched in the last month.

- **Contradictions**: pages in the same topic area making opposing claims. Name both pages and the claim.
- **Weak links**: a page mentions a topic that has its own page but does not link it.
- **Tag entropy**: near-duplicate tags (`ml`, `machine-learning`); propose one canonical form per group.
- **Sensitivity drift**: a downstream page repeats identifying or sensitive detail that should have stayed on the source page; a `shareable` page cites nothing but `personal` sources without visible abstraction.
- **Empty sections**: template sections left with placeholder prose.

### 3. Report

```markdown
# Wiki lint — YYYY-MM-DD

## Summary
<N> pages — <sources/entities/concepts/synthesis>. <E> errors, <W> warnings. <U> files waiting in raw/inbox.

## Errors
### <type>
- <path>:<line> — <what and the offending value>

## Warnings
### <type>
- <path> — <detail>

## Judgment findings
- <contradiction | weak link | tag | sensitivity | empty section> — <pages> — <one-line proposal>

## Info
- Counts, distributions, scale proximity, last log entry
```

Order findings so the owner can jump to fixes: errors first, then warnings, then judgment findings, then info. If nothing is wrong, say so in one line.

### 4. Log

Append one entry, never the full report:

```markdown
## [YYYY-MM-DD] lint | <E> errors, <W> warnings

Errors: <one line or none>
Warnings: <one line or none>
Judgment: <one line or none>
```

Apply the maintenance nudge rule; lint reporting more than five errors is itself a reason to suggest `wiki-evolve`.

## Do not

- Fix anything, even a one-character broken link. Report and offer.
- Delete orphans; the owner may want them.
- Skip the script and eyeball the structure instead; the script is the source of truth for mechanical checks.
