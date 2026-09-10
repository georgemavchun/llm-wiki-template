# Onboarding

Everything you need for the first hour with your new wiki, step by step. For the short version, see the [README](../README.md).

## Prerequisites

Check each before you start:

```bash
git --version
python3 --version
claude --version
```

You need git, Python 3.9 or newer, and Claude Code. If `python3 --version` shows something older than 3.9, install a newer Python before continuing; the tooling depends on it. If `claude --version` fails, install Claude Code first.

## Create your copy

1. Open the template repository on GitHub.
2. Click **Use this template**, then **Create a new repository**. Do not click **Fork**: a fork inherits the template's git history, and a colleague looking at your wiki's history should see only your own content. "Use this template" gives you a clean history instead.
3. Name it, choose an owner, and set visibility to **Private**. A personal wiki holds notes about people and work; there is no reason for it to be public. See [privacy.md](privacy.md) for why.
4. Create the repository.

## Clone it

```bash
git clone <your-new-repository-url>
cd <your-new-repository-directory>
```

## Run bootstrap

```bash
python3 scripts/bootstrap.py --owner "Your Name"
```

Bootstrap is idempotent: run it again any time and it reports what it already did instead of redoing it. Each step prints one line:

- `[done]`: the step made a change just now.
- `[already]`: the step found nothing to do; a previous run, or the template itself, already covers it.
- `[skipped]`: the step does not apply here (hooks are skipped outside a git repository, or with `--skip-hooks`).
- `[failed]`: the step could not complete; read the message and fix the cause before continuing.

A typical first run looks like this:

```
[done] python-version: python 3.12.4 (>= 3.9 required)
[done] git-repo: inside a git work tree
[done] placeholders: replaced placeholders in wiki/CLAUDE.md, wiki/LOG.md, README.md, CUSTOMIZATIONS.md
[done] hooks: core.hooksPath=scripts/hooks; pre-commit made executable
[done] dirs: created .staging; already present: wiki/raw/inbox
Wiki: 0 pages (0 sources, 0 entities, 0 concepts, 0 synthesis) · 0 errors · 0 warnings · 1 file in raw/inbox
Last log: [2026-09-10] bootstrap | wiki created from llm-wiki-template
[done] lint: ran wiki_lint.py --brief
[done] tests: 171 tests passed

Next steps
  1. Open Claude Code here
  2. Say "ingest the inbox"
  3. Then "lint the wiki"
```

If `tests` reports `[failed]` or `lint` shows errors, stop and read the output before going further. Do not build on a broken copy.

## What the status line looks like

Every time you open Claude Code in this folder, a `SessionStart` hook prints a short status:

```
Wiki: 3 pages (1 sources, 1 entities, 1 concepts, 0 synthesis) · 0 errors · 0 warnings · 0 files in raw/inbox
Last log: [2026-09-10] ingest | Welcome to your LLM wiki

Read wiki/CLAUDE.md before editing the wiki; use the wiki-* skills for every operation.
```

This comes from `scripts/hooks/session_start.py`, built on the same lint script you can run yourself. If it is missing or shows a stale count, something about the hook or the wiki root is misconfigured; see the troubleshooting table below.

## Your first ingest

The template ships one tutorial source at `wiki/raw/inbox/2026-09-10-welcome-to-your-llm-wiki.md`. It describes the LLM wiki pattern itself, so after ingesting it you can compare the result to what you just read.

Say:

```
ingest the inbox
```

Expect the agent to:

1. Read the schema (`wiki/CLAUDE.md`) and the source in full.
2. Run the privacy scanner on it (it passes; the tutorial source is clean).
3. Move it from `wiki/raw/inbox/` to `wiki/raw/`.
4. Write one page under `wiki/sources/`.
5. Create one or two pages under `wiki/concepts/` and `wiki/entities/`. Lazy creation means it will not make a page for every passing mention.
6. Update `wiki/INDEX.md` and append one entry to `wiki/LOG.md`.
7. Run `wiki_lint.py --brief` and report zero errors.

If the agent pauses to ask you something, for example whether a borderline mention deserves its own page, answer in a sentence or two. This is the "discuss briefly" step the ingest skill uses for ordinary documents, and it happens once per source.

## First query

```
what does the wiki say about the LLM wiki pattern
```

Expect an answer with `[[page]]`-style citations, built from the pages you just created rather than by re-reading the source. The agent may offer to file the answer as a new page; saying no is fine.

## First lint

```
lint the wiki
```

Expect a short report (errors, warnings, judgment findings) and one new line in `wiki/LOG.md`. Lint never fixes anything; it only reports.

## First commit

```bash
git add -A
git commit -m "ingest: welcome tutorial"
```

A pre-commit hook runs automatically, installed by bootstrap. It:

- refuses to commit anything under `.staging/`;
- refuses a modified or deleted file under `wiki/raw/` unless `WIKI_ALLOW_RAW_CHANGE=1` is set, see [privacy.md](privacy.md);
- runs the privacy scanner on every staged wiki file;
- runs `gitleaks` on the staged diff, if it is installed.

If everything passes it prints `pre-commit: ok` and the commit proceeds.

## A daily rhythm

- New source lands (article, PDF, transcript): drop it in `wiki/raw/inbox/` and say "ingest the inbox".
- A quick fact or quote comes up in conversation: say "quick note: ...", handled by `wiki-ingest-light`.
- A working session with Claude Code ends with a decision or a finding worth keeping: say "crystallize this".
- Weekly, or after a batch of ingests: say "lint the wiki".

## What never goes in

Never store, even temporarily in `wiki/raw/`: passwords, API keys, tokens or recovery phrases; passport, tax or national ID numbers; full card or bank account numbers; health or medical details about an identifiable person; anyone's compensation; privileged legal advice; anything said off the record. The privacy scanner catches part of this deterministically; the rest depends on you and the agent applying judgment together. The full reasoning is in [privacy.md](privacy.md); the canonical list lives in [../wiki/CLAUDE.md](../wiki/CLAUDE.md).

## Obsidian, in five lines

Open the `wiki/` folder, not the repository root, as an Obsidian vault. The graph view shows how pages link together and highlights orphan pages. The Web Clipper can save a web page straight into `wiki/raw/inbox/` for the agent to ingest later. `.obsidian/`, Obsidian's own workspace state, is already in `.gitignore`, so it never gets committed. Obsidian is a reading and browsing surface only; it does not write wiki pages, the agent does.

## Troubleshooting

| Problem | What is happening | What to do |
|---|---|---|
| A commit was blocked by the pre-commit hook | One of the checks in "First commit" above failed | Read the stderr message and fix the cause: unstage `.staging/`, unset `WIKI_ALLOW_RAW_CHANGE`, or handle the flagged content. Bypass only with `git commit --no-verify`, and only if you are sure. |
| A write was blocked while the agent was editing | `guard_write.py` refused a write under `wiki/raw/`, or content that tripped the scanner | Do not ask the agent to work around it. If it is a false positive on ordinary content, say so and let it rephrase. If the target was `wiki/raw/`, the fix is always to stage, scan, then move the file, never to edit it in place. |
| A source was blocked at ingest ("preflight blocked") | `privacy_preflight.py` exited `2` | Read the category and reason code the agent reports, never the value. Decide: redact and retain, keep a sanitized extract, or keep only a pointer. Exit `1` means the scan itself failed to run; fix that first. |
| Tests fail right after bootstrap | Something in your environment differs from the template's assumptions | Read the failing test names. A common cause is an old Python; check `python3 --version` again. |
| Placeholders like `{{OWNER_NAME}}` are still visible | Bootstrap has not run, or ran before you answered the owner prompt | Run `python3 scripts/bootstrap.py --owner "Your Name"` again; it is safe to repeat. |
| `python3: command not found` | Python is not installed, or only available as `python` | Install Python 3.9 or newer, or use whichever command your system provides, consistently, everywhere this guide shows `python3`. |
| The agent tried to edit a file under `wiki/raw/` | It forgot the raw-immutability rule | It should self-correct; `.claude/rules/raw-immutability.md` and the write guard both stop it before anything is written. If it insists, stop it and point it at that rule. |

Next: [skills.md](skills.md) for what each skill does in full, or [customizing.md](customizing.md) once you want to adapt the template.
