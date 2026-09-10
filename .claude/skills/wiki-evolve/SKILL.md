---
name: wiki-evolve
description: Use when the wiki's rules, templates or structure — not its content — should be reviewed: the `LOG.md` nudge says "consider running wiki-evolve", roughly every twenty log entries, after lint reported many errors, or when the user says "evolve the wiki", "review the wiki system", "are the conventions still right". Proposes changes; applies nothing without per-proposal approval.
---

# Wiki Evolve

Meta-review of the wiki **system**. Lint asks whether the pages are healthy; evolve asks whether the schema, templates, skills and directory structure are still the right ones. This is the only skill allowed to propose edits to `wiki/CLAUDE.md`, and it never applies them silently.

## Workflow

### 1. Gather data

```bash
python3 scripts/wiki_lint.py --wiki-root wiki --format json
```

Read `wiki/CLAUDE.md`, `wiki/LOG.md`, `wiki/INDEX.md`, `wiki/_templates/*.md`, `wiki.config.json`, and `git log --oneline -- wiki/CLAUDE.md` (direct owner edits since the last evolve). From the log derive the operation mix (ingest / ingest-light / crystallize / lint / share), ingest cadence, page-creation rate, and how often each page family grows. From the lint JSON take page counts per directory, size distribution, reliability and sensitivity distributions, orphan and Pending Review backlog, inbox age. From the pages sample frontmatter compliance: which fields are always filled, which are always empty, which template sections stay as placeholders. Read the previous `## [date] evolve |` entries for proposals that were applied and their target metrics.

### 2. Analyze

Three lenses, every finding grounded in a number:

- **Ideality and trimming.** What effort could be automated? Which template fields, sections, directories, rules or skills are unused? A convention nobody follows is a candidate for removal, not a reminder.
- **Contradictions.** Where does the system demand two incompatible things ("fast entry" versus "rich frontmatter")? Resolve by design (defaults, scripts), not by exhortation.
- **Evolution patterns.** What repeated behaviour wants to become a template, a page family, a skill or a script? Which scale threshold is near?

Self anti-patterns to check explicitly: schema bloat (line count trend of `wiki/CLAUDE.md`), skill sprawl, rules that lint could enforce but does not, Pending Review accumulation, inbox aging, sensitivity drift.

### 3. Verify the last round

For each proposal applied at the previous evolve, did its target metric move? Say so, with the numbers.

### 4. Propose

```markdown
## Proposal: <short title>

Signal: <the numbers that triggered this>
Lens: ideality | contradiction | trimming | evolution
Change: <exact files and edits>
Target metric: <what should move, by when>
Risk: low | medium | high — <what could go wrong> — Rollback: <how>
```

"System in steady state, no proposals" is a valid result. Do not invent findings. Prefer removals as readily as additions, and small reversible changes over restructurings. A proposal that adds owner friction needs a strong justification.

### 5. Apply only what is approved, one at a time

Before any change to `wiki/CLAUDE.md`: tag the repository `wiki/pre-evolve-YYYY-MM-DD` as a rollback point and show the diff. After a template or structure change, update affected pages surgically and `INDEX.md` if the structure moved. Record the change in `CUSTOMIZATIONS.md`.

### 6. Log

```markdown
## [YYYY-MM-DD] evolve | <n> proposals, <a> applied

Metrics: <snapshot: pages, ops mix, backlog>
Prior round: <metric outcomes>
Applied: <titles>
Deferred: <titles — reason>
Rejected: <titles — reason>
Schema edited: yes | no
```

## Do not

- Apply a schema change without explicit approval of that specific proposal.
- Propose from taste. "I think X is nicer" is not a signal; "X is empty on 80% of pages" is.
- Run evolve on content problems; that is lint.
