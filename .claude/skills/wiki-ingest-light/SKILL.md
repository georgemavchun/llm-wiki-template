---
name: wiki-ingest-light
description: Use when the user drops a short fragment into the conversation — a chat snippet, a quote, a fleeting thought, a two-line update, a quick excerpt from a ticket or document — or says "quick note", "file this snippet", "remember this", "drop this in the wiki", "ingest-light this". For substantive sources (articles, PDFs, transcripts, long pastes) use `wiki-ingest` instead.
---

# Wiki Ingest-light

Low-ceremony path for fragments. No source page, no discussion step, append-only routing into existing pages, a high bar for creating new ones. Speed matters, the privacy gate does not move.

## Always do this first

1. Read `wiki/CLAUDE.md` (lazy page creation, sensitivity, untrusted sources).
2. Read `wiki/INDEX.md`.

## Workflow

### 1. Save the original to staging and scan it

If the user pasted text, write it to `.staging/YYYY-MM-DD-<three-to-five-word-slug>.md` with a header:

```
captured: YYYY-MM-DD
origin: <who said or wrote it, if known>
kind: fragment
```

If it is already a file under `wiki/raw/inbox/`, scan it in place.

```bash
python3 scripts/privacy_preflight.py <file> --quiet
```

Exit `0` → continue. Exit `2` → write nothing; report category, reason and line only; ask the owner whether to redact, drop, or keep a pointer. Exit `1` → fix and re-run.

### 2. Place it

```bash
mv .staging/<name>.md wiki/raw/<name>.md
```

The raw file is the record for a fragment; there is no `sources/` page.

### 3. Route the fragment

Pick the pages this fragment affects from the index (use `python3 scripts/wiki_search.py "<key terms>"` when the index is long).

**Relevant pages exist:**

1. Read each affected page.
2. Surgical `Edit`: add a dated bullet or short section citing the raw file: `From [<name>.md](../raw/<name>.md) (YYYY-MM-DD): …`.
3. Revise the page's summary or key claims only if the fragment changes them.
4. Add a cross-link if the fragment connects two previously unlinked pages.
5. Bump `updated:`.

**No relevant page exists:**

- Substantial, or clearly about something that will recur → create one page with `python3 scripts/new_page.py …`, fill it, add it to `INDEX.md`.
- An isolated fact → leave it in `raw/` only; the next ingest that touches the topic will pick it up. Say so in the log entry.
- Genuinely unsure → ask: "This does not fit anywhere yet. Create a page, file it under [[<closest>]], or leave it in raw?"

Sensitivity: a fragment about an identifiable person's health, pay, performance or private life is `personal`; file only a neutral abstraction on downstream pages, or nothing.

### 4. Log

```markdown
## [YYYY-MM-DD] ingest-light | <brief description>

Updated: [[page-1]], [[page-2]]
New: [[new-page]]            (omit when none)
Raw only: raw/<name>.md      (when nothing was routed)
```

Apply the maintenance nudge rule from the schema.

### 5. Report

One or two sentences: which pages changed, any sensitivity concern.

## Do not

- Create a `sources/` page; that is what makes this light.
- Discuss before filing unless routing is ambiguous or the scan blocked.
- Create pages eagerly; the threshold is higher than for full ingest.
- Translate the fragment; the raw file keeps its language, the page text follows the schema's language policy.
- Skip the scan because the fragment is short. Short is where pasted tokens hide.
