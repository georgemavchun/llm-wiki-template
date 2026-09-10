# Skills

Every wiki operation is a Claude Code skill under `.claude/skills/wiki-*/`. Say the trigger phrase and the matching skill loads; you rarely need to name it. This page summarizes each one. The skill file itself is the operating procedure the agent actually follows.

## wiki-setup

For: bringing a fresh or half-configured copy to a working state.
Say: "set up my wiki", "bootstrap the wiki", "finish setup", "onboard me".
Inputs: your name (asked once if not given); whether you want a team wiki destination.
Writes: placeholders filled in `wiki/CLAUDE.md`, `wiki/LOG.md`, `README.md`, `CUSTOMIZATIONS.md`; git hooks installed; `.staging/` and `wiki/raw/inbox/` created.
Never: creates or changes the visibility of a remote repository; edits `wiki/CLAUDE.md` beyond the language-policy paragraph, and only if asked.
Runs: `scripts/bootstrap.py`.

> You: "set up my wiki, I'm Alex Chen"
> Agent: runs bootstrap, reports each step, asks about language policy and a team wiki, offers to ingest the tutorial source.

Full detail: [../.claude/skills/wiki-setup/SKILL.md](../.claude/skills/wiki-setup/SKILL.md).

## wiki-ingest

For: adding one substantive source (a file, URL, PDF, transcript, or a long paste) to the wiki.
Say: "ingest this", "add this source", "process the inbox", "drain the inbox", "read this into the wiki".
Inputs: a file already in `wiki/raw/inbox/`, a path, a URL, or pasted text.
Writes: a page under `wiki/sources/`; surgical edits to entity and concept pages; `wiki/INDEX.md`; one `wiki/LOG.md` entry.
Never: writes into `wiki/raw/` before the scanner clears the file; marks a page `reliability: high` from one source; rewrites an existing page instead of editing it surgically.
Runs: `scripts/privacy_preflight.py`; for transcripts, `scripts/validate_privacy_ledger.py`; `scripts/new_page.py`; `scripts/wiki_lint.py --brief` to verify.

> You: "ingest the inbox"
> Agent: scans the file, moves it into `wiki/raw/`, reads it, writes the source page and touches two concept pages, updates the index and log, reports zero lint errors.

Full detail: [../.claude/skills/wiki-ingest/SKILL.md](../.claude/skills/wiki-ingest/SKILL.md).

## wiki-ingest-light

For: a short fragment, such as a chat snippet, a quote, or a two-line update.
Say: "quick note", "file this snippet", "remember this", "drop this in the wiki", "ingest-light this".
Inputs: pasted text, or a file already in the inbox.
Writes: a raw fragment file; a surgical edit to an existing page, if one fits; one `wiki/LOG.md` entry.
Never: creates a `wiki/sources/` page; discusses before filing unless routing is ambiguous or the scan blocked; skips the scan because the text is short.
Runs: `scripts/privacy_preflight.py --quiet`.

> You: "quick note: the vendor confirmed the new API rate limit is 500 req/min"
> Agent: scans it, files it as a dated bullet on the relevant page, reports which page changed.

Full detail: [../.claude/skills/wiki-ingest-light/SKILL.md](../.claude/skills/wiki-ingest-light/SKILL.md).

## wiki-ingest-meetings

For: pulling several meeting or call recordings from a recorder in one batch.
Say: "ingest new meetings", "load my calls", "sync recordings", "process this week's meetings".
Inputs: a recorder adapter under `references/adapters/` (shipped: Jamie); the recorder's own marker for "already ingested".
Writes: nothing directly; it stages each transcript and hands it to `wiki-ingest`, then applies the recorder's markers.
Never: decides "new" by date instead of the recorder's marker; copies a recorder-generated task list without checking it against the transcript.
Runs: the adapter's discovery calls, then everything `wiki-ingest` runs, once per meeting.

> You: "pull new meetings from Jamie"
> Agent: lists new recordings, stages and ingests each one, tags the ingested ones, reports a batch table of ingested, skipped and blocked.

Full detail: [../.claude/skills/wiki-ingest-meetings/SKILL.md](../.claude/skills/wiki-ingest-meetings/SKILL.md). Adapter: [../.claude/skills/wiki-ingest-meetings/references/adapters/jamie.md](../.claude/skills/wiki-ingest-meetings/references/adapters/jamie.md).

## wiki-crystallize

For: filing durable signal from the conversation itself, such as a decision, a definition, a finding, or an open question.
Say: "crystallize this", "file what we figured out", "save this to the wiki", "we should remember this".
Inputs: the conversation so far.
Writes: a surgical edit to an existing concept or entity page (the default), or a new `wiki/concepts/` or `wiki/synthesis/` page; one `wiki/LOG.md` entry.
Never: paraphrases an opinion as a fact; files a draft decision as decided; rewrites an existing page instead of adding to it.
Runs: `scripts/new_page.py` for a new page; `scripts/wiki_lint.py --brief` to verify.

> You: "crystallize this, we decided to keep the staging directory outside git entirely"
> Agent: lists the one decision found, confirms placement, edits the relevant page, logs it.

Full detail: [../.claude/skills/wiki-crystallize/SKILL.md](../.claude/skills/wiki-crystallize/SKILL.md).

## wiki-query

For: answering a question from the wiki.
Say: "what do we know about X", "what does the wiki say about Y", "according to the wiki...", "did we decide Z".
Inputs: your question.
Writes: nothing, unless you agree to file the synthesis as a page.
Never: synthesizes from raw sources when wiki pages already exist; hides a contradiction between two pages; auto-files an answer.
Runs: `scripts/wiki_search.py` once the index is large, or the `wiki-scout` subagent; `scripts/new_page.py` and `scripts/wiki_lint.py --brief` only if you choose to file.

> You: "what does the wiki say about the LLM wiki pattern"
> Agent: reads the index, opens the relevant pages, answers with `[[slug]]` citations, offers to file the synthesis.

Full detail: [../.claude/skills/wiki-query/SKILL.md](../.claude/skills/wiki-query/SKILL.md).

## wiki-lint

For: a health check of the wiki.
Say: "lint the wiki", "wiki status", "is the wiki healthy", "check for broken links".
Inputs: none.
Writes: nothing but one `wiki/LOG.md` line; the report itself is not saved anywhere.
Never: fixes anything it finds, even a one-character broken link; deletes an orphan page.
Runs: `scripts/wiki_lint.py`.

> You: "lint the wiki"
> Agent: runs the script, reports errors, warnings and a few judgment findings such as contradictions or weak links, logs one line.

Full detail: [../.claude/skills/wiki-lint/SKILL.md](../.claude/skills/wiki-lint/SKILL.md).

## wiki-evolve

For: reviewing the wiki's own rules, templates and structure, not its content.
Say: "evolve the wiki", "review the wiki system", "are the conventions still right", or when the log's own nudge suggests it (roughly every twenty entries).
Inputs: `wiki/LOG.md` history, `wiki_lint.py --format json`, git history of `wiki/CLAUDE.md`.
Writes: numbered proposals; applies a schema or template change only after you approve that specific proposal, tagging the repository first as a rollback point.
Never: applies a schema change without your approval; proposes from taste instead of a measured signal.
Runs: `scripts/wiki_lint.py --format json`.

> You: "evolve the wiki"
> Agent: reports the operation mix and page-growth numbers, proposes two changes with the signal behind each, applies only the one you approve.

Full detail: [../.claude/skills/wiki-evolve/SKILL.md](../.claude/skills/wiki-evolve/SKILL.md).

## wiki-share

For: exporting sanitized extracts to a team or project wiki configured in `wiki.config.json`.
Say: "share this with the team wiki", "sync the team wiki", "push what's shareable", "what could go to the project wiki".
Inputs: `wiki.config.json → share.destinations` (inactive when empty).
Writes: extract files at the destination, only after you confirm the exact list in the same run; a `share-status` marker on the affected `wiki/LOG.md` entries.
Never: writes to a destination without your per-run confirmation, even for the safest batch; lets your approval override quarantine or personal-data risk.
Runs: the ledger-and-validator pipeline described in [../.claude/skills/wiki-ingest/references/transcript-ledger.md](../.claude/skills/wiki-ingest/references/transcript-ledger.md); `scripts/validate_privacy_ledger.py`.

> You: "what could go to the team wiki"
> Agent: says no destinations are configured yet and points you at [customizing.md](customizing.md), or, once configured, lists candidates grouped by risk and asks which to push.

Full detail: [../.claude/skills/wiki-share/SKILL.md](../.claude/skills/wiki-share/SKILL.md). Taxonomy: [../.claude/skills/wiki-share/references/sensitivity-taxonomy.md](../.claude/skills/wiki-share/references/sensitivity-taxonomy.md).

## wiki-scout

`wiki-scout` is a separate, read-only subagent (model: haiku), not a skill you invoke directly. `wiki-query` and `wiki-ingest` may delegate to it once the index is long, a question spans several topics, or an ingest needs to locate pages for surgical edits before writing. It runs `scripts/wiki_search.py`, reads `wiki/INDEX.md`, opens only the frontmatter and the first heading of each candidate, and returns a ranked list of at most ten pages with a one-line reason each. It never modifies a file, never reads `wiki/raw/`, and never quotes more than one line from a page. Definition: [../.claude/agents/wiki-scout.md](../.claude/agents/wiki-scout.md).

## Scripts reference

| Script | Purpose | Exit codes |
|---|---|---|
| `scripts/wiki_lint.py` | Deterministic health check: frontmatter, enums, caps, broken links, index membership, staleness, placeholders | `0` clean, `2` errors, `1` could not run |
| `scripts/wiki_search.py` | BM25 keyword search over wiki content pages | `0` always |
| `scripts/new_page.py` | Scaffold a page from its family's template | `0` created, `1` page exists or input invalid |
| `scripts/bootstrap.py` | Idempotent first-run setup | `0` every mandatory step succeeded, `1` otherwise |
| `scripts/privacy_preflight.py` | Scan files or stdin for quarantine-tier content, never printing the match | `0` pass, `2` blocked, `1` could not run |
| `scripts/validate_privacy_ledger.py` | Validate a transcript classification ledger against its source's hash and line count | `0` valid, `2` invalid, `3` valid but contains quarantine, `1` could not run |
| `scripts/hooks/guard_write.py` | Claude Code `PreToolUse` hook: blocks writes under `wiki/raw/` and writes that trip the scanner | `0` allow, `2` block; an internal error exits `1` (non-blocking) |
| `scripts/hooks/session_start.py` | Claude Code `SessionStart` hook: prints the wiki status brief | always `0` |
| `scripts/hooks/pre-commit` | git hook: staging-area check, raw add-only check, scanner, optional gitleaks | `0` ok, `1` blocked |

Each script's full CLI is in its own `--help` output. See [customizing.md](customizing.md) for how these scripts read `wiki.config.json`.
