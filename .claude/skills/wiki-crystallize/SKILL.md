---
name: wiki-crystallize
description: Use when durable signal was produced in the conversation itself rather than in an external source — a decision, a definition, a finding, an open question worth tracking — and the user says "crystallize this", "file what we figured out", "save this to the wiki", "we should remember this", or a substantive working session is ending. For external sources use `wiki-ingest`.
---

# Wiki Crystallize

Distil what a conversation established into wiki pages. The conversation is ephemeral; the page becomes the only record.

## Always do this first

1. Read `wiki/CLAUDE.md`.
2. Read `wiki/INDEX.md` so you add to existing pages instead of duplicating.

## Workflow

### 1. Identify the durable signal

Keep: decisions and their reasoning; definitions agreed on; findings established together; open questions worth tracking; anything not obvious from code, files or history.

Drop: session-local trivia; anything already documented; vague impressions; tentative "we will think about it" items (file those under `## Pending Review` or skip); anything the user said to forget.

If you cannot name at least one concrete decision, finding or definition, say there is nothing to crystallize.

### 2. Decide placement

- Existing concept or entity page covers it → surgical `Edit`, a new dated `## <section>` in the right place. This is the default.
- Cross-cutting analysis with no single home → new `synthesis/` page.
- A reusable definition or pattern → new `concepts/` page.
- A new `entities/` page is rare here; entities usually come from sources.

Apply lazy creation. Check sensitivity: a decision about an identifiable person's pay, performance or private circumstances is `personal` and gets a neutral abstraction at most.

### 3. Confirm before writing

List the signals, where each goes (existing page vs new), and what you skipped and why. Wait for the owner to confirm or adjust. When running unattended, write with `reliability: medium` and record the placement rationale in the log entry instead.

### 4. Write

- New pages: `python3 scripts/new_page.py <family> <slug> --title "…" --source conversation:YYYY-MM-DD`.
- Frontmatter: `reliability: medium` unless the conversation verified the claim against sources; `sources: ["conversation:YYYY-MM-DD"]` plus any wiki pages the conversation drew on; `sensitivity` per the schema.
- Opinions stay attributed: "Owner's view (as of YYYY-MM-DD): …", never "X is true".
- Date time-bound facts.

### 5. Index, log, verify

Add new pages to `INDEX.md`. Append:

```markdown
## [YYYY-MM-DD] crystallize | <topic>

Created: [[new-page]]
Updated: [[existing-page]]
Decisions filed: <count>
```

Run `python3 scripts/wiki_lint.py --wiki-root wiki --brief` and fix any error you introduced.

### 6. Report

New and modified files, anything under `## Pending Review`.

## Do not

- Crystallize eagerly; an empty result is a valid result.
- Paraphrase an opinion as a fact.
- File a draft decision as decided.
- Rewrite an existing page; add to it.
