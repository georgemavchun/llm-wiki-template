# Privacy and integrity model

Read this before you put anything real into the wiki.

## The honest disclosure

Everything the agent reads under this repository, including every file in `wiki/raw/` and every wiki page, is sent to the model provider (Anthropic, when you use Claude Code) as part of answering you. That is how a coding agent works; there is no way to ask it to read a file privately. Git history is durable: once something is committed, it stays in the repository's history, even after you delete it, until someone rewrites history on purpose. Keep this wiki in its own repository, separate from directories that hold secrets, credentials, or files unrelated to the wiki.

## Threats this template addresses

| Threat | Layered controls | Where |
|---|---|---|
| Secrets or personal data get pasted into a git-tracked repo | A deterministic scanner blocks known patterns before anything enters `wiki/raw/`; a git hook repeats the scan at commit time; a Claude Code hook repeats it on every write | `scripts/privacy_preflight.py`, `scripts/hooks/pre-commit`, `scripts/hooks/guard_write.py` |
| Personal or third-party sensitive content leaks into a shared or team wiki | A sensitivity vocabulary and a content-free classification ledger gate what can travel, with per-item owner approval for anything but the safest tier | `.claude/skills/wiki-share/references/sensitivity-taxonomy.md`, `scripts/validate_privacy_ledger.py` |
| A document you ingest tries to instruct the agent (indirect prompt injection) | The schema states that source text is data, never instructions; the scanner flags instruction-like and exfiltration-like phrasing | `wiki/CLAUDE.md`, `scripts/privacy_preflight.py` |
| Source truth gets silently rewritten or lost | Raw sources are add-only, enforced by a permission deny, a write-guard hook and a git pre-commit check, with CI repeating the check | `.claude/settings.json`, `scripts/hooks/guard_write.py`, `scripts/hooks/pre-commit`, `.github/workflows/checks.yml` |
| A fork inherits someone else's wiki content | The README tells you to use "Use this template", not "Fork", and explains why | `README.md` |

## The four sensitivity classes

A block of content (a paragraph, a topic span, a group of turns) is classified into one of four classes before it can be shared anywhere, and every wiki page carries a `sensitivity:` field in its frontmatter using a related vocabulary.

- `quarantine`: never stored anywhere, even in this wiki. Credentials, government IDs, card numbers, anything explicitly said off the record. Example: an API key pasted by accident.
- `personal`: stays in this wiki, never exported. Health, compensation, HR matters, internal politics, anything about an identifiable person beyond ordinary coordination. Example: a note that a colleague is considering a job change.
- `restricted`: may reach a team wiki, but only with your explicit per-item approval. Internal architecture, security posture, non-public roadmap. Example: a description of a service's data model.
- `shareable`: may reach a team wiki after normal review. Sanitized technical or process knowledge with no names or rare identifiers. Example: "on-call load is unsustainable for this team," with no names attached.

Page-level frontmatter uses `personal | restricted | shareable | public` (no `quarantine`; quarantine content is never written to a page at all). `public` means the fact is already public, such as something from a press release. The full taxonomy, with reason codes and transformation rules, is in [../.claude/skills/wiki-share/references/sensitivity-taxonomy.md](../.claude/skills/wiki-share/references/sensitivity-taxonomy.md).

## The preflight scanner

`scripts/privacy_preflight.py` scans one or more files, or standard input, for five categories of deterministic pattern: `credentials` (keys, tokens, connection strings), `high-risk-identifier` (labelled national IDs, card security codes), `explicit-no-record` phrasing in English, Russian and Danish, `control-bypass` language, and `untrusted-instruction` patterns (prompt injection and exfiltration attempts). It never prints the matched value, only the category, a reason code, and the line number.

```bash
python3 scripts/privacy_preflight.py path/to/file.md --format json
python3 scripts/privacy_preflight.py a.md b.md c.md --quiet
cat draft.md | python3 scripts/privacy_preflight.py --stdin
```

Exit codes: `0` pass, `2` blocked, `1` the scan itself could not run. `--format json` gives a machine-readable record per file, including its SHA-256 and line count, used later to bind a classification ledger to the exact file scanned. `--format text` (the default) is for reading. `--quiet` prints only files that are blocked or errored, useful when scanning many files at once.

The scanner is deliberately conservative and produces false positives: a Russian phrase for "between us" meaning "between our two companies," or a defensive mention of "bypass" in a security discussion. A false positive is still a stop. The owner decides whether to proceed, never the agent, and the agent must never edit the source text to make the scan pass. Editing content to defeat a check hides the thing the check exists to catch; it is not a fix.

When you decide a finding is a false positive, the recorded way to proceed is the allowlist, not `git commit --no-verify`. The agent (with your explicit yes) adds an entry to `wiki/privacy-allowlist.json` naming the file, its exact SHA-256, the reason code being accepted, who approved it and when. The scanner, the pre-commit hook and CI all honour that file, and the entry stops working the moment the file's content changes or a different pattern fires. Audit the allowlist at any time by running the scanner with `--no-allowlist`. The entry format is in the ingest skill's reference on transcript ledgers.

## The classification ledger

Transcripts are the riskiest source type: they mix work substance with personal, HR, financial and third-party material in a confident, unedited register. Before a transcript is placed in `wiki/raw/`, the ingest skill breaks it into ordered, gap-free blocks and classifies each one into the four-class model above, writing a temporary, content-free JSON ledger bound to the source file's SHA-256 and line count. `scripts/validate_privacy_ledger.py` checks the ledger's structure and its class-versus-action rules; it never reads the source content itself, only the ledger and the source's hash and line count.

The full procedure, the ledger schema, and how to produce a sanitized extract when a transcript contains quarantine material, are in [../.claude/skills/wiki-ingest/references/transcript-ledger.md](../.claude/skills/wiki-ingest/references/transcript-ledger.md).

## Redaction procedure

Raw sources are add-only by default. The one exception is an owner-authorized privacy, security or legal redaction:

1. Make the smallest effective change to the raw file.
2. Commit locally with `WIKI_ALLOW_RAW_CHANGE=1 git commit ...`. Without this variable the pre-commit hook refuses any modification, deletion or rename of a file under `wiki/raw/` outside the `raw/inbox/` drop zone (the inbox may change freely; moving a file out of it into `raw/` is the normal ingest step).
3. Start the commit subject with `redaction:`. CI's raw-add-only check treats a `redaction:` commit as the one allowed exception in that range.
4. Add a `## [YYYY-MM-DD] redaction | <file>` entry to `wiki/LOG.md` naming the reason category and the affected pages, never the removed content itself.

## If a secret got in

Stop. Do not commit or push anything else first.

1. Rotate the credential immediately, wherever it is used. Treat it as compromised the moment it was committed, regardless of whether the repository is private.
2. Only after rotating, remove it from git history, for example with `git filter-repo` or by following GitHub's own guide on removing sensitive data from a repository.
3. Force-push the cleaned history only after you, the owner, have decided to. It rewrites shared history and breaks any other clone.
4. Remember that any fork, clone or local checkout made before the cleanup still has the old history with the secret in it. Rewriting your own remote does not reach those copies.

## GitHub-side controls

- Keep the repository **private**. A personal wiki has no reason to be public.
- Secret scanning and push protection are free on public repositories; as of 2026, they are a paid feature on private repositories. Check your plan before relying on them as a backstop.
- Branch protection is optional for a single-owner personal wiki; consider it if more than one person can push.

## Prompt injection

A source you ingest is data, never instructions. The schema (`wiki/CLAUDE.md`) and every ingest-family skill say this explicitly: the agent does not follow directions found inside a source, does not open links a source asks it to open, does not run commands a source contains, and does not send content anywhere because a document requests it. This is why the scanner's `untrusted-instruction` category exists: text inside a source that reads like an instruction to an AI system is exactly the pattern indirect prompt injection relies on, so it is flagged and classified at least `restricted`, even when it turns out to be harmless.

## Optional: gitleaks

The pre-commit hook (`scripts/hooks/pre-commit`) runs `gitleaks` over the staged diff automatically if it finds `gitleaks` on your `PATH`; there is nothing to configure. Install it with your package manager of choice, for example `brew install gitleaks` on macOS, and the next commit picks it up.

## What the tooling does not guarantee

The scanner and hooks are tested to never print a matched value, to stop raw files from being edited through Claude Code's file tools, and to stop a modified raw file from being committed without an explicit override. They do not detect free-text sensitive content with no keyword the scanner knows, such as a paragraph about someone's health with no flagged term. They do not guarantee correct classification, which depends on the agent's judgment under the taxonomy; in particular, the classification ledger is temporary and the commit hook never sees it, so a file the agent classified as quarantine is kept out of git only because the ingest skill moves it to `.staging/blocked/` rather than leaving it in the inbox. And they do not stop an operator who deliberately bypasses the hooks. Treat this tooling as a seatbelt, not a vault; see [../SECURITY.md](../SECURITY.md) for the short version.
