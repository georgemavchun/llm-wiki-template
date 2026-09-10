---
name: wiki-setup
description: Use when a wiki copy is new or half-configured — placeholders such as {{OWNER_NAME}} are still present, git hooks are not installed, `.staging/` is missing, the session-start status shows errors on a fresh copy, or the user says "set up my wiki", "bootstrap the wiki", "finish setup", "onboard me".
---

# Wiki Setup

Bring a fresh copy of the template to a working state. The deterministic part is `scripts/bootstrap.py`; this skill wraps it with the two decisions only the owner can make.

## Steps

1. **Find out who the owner is.** Use the name the user gave; otherwise ask once. Do not guess from the git config without saying so.
2. **Run the bootstrap** from the repository root:

   ```bash
   python3 scripts/bootstrap.py --owner "<Owner Name>" --yes
   ```

   It replaces placeholders, installs the git hooks (`core.hooksPath scripts/hooks`), creates `.staging/` and `wiki/raw/inbox/`, prints the lint summary and runs the tooling tests. It is idempotent; re-running is safe.
3. **Read the output.** If tests fail or lint reports errors, report them verbatim and stop; do not continue setup on a broken copy.
4. **Language policy.** Show the owner the "Language policy" paragraph of `wiki/CLAUDE.md` and ask whether pages should stay English. If they want pages in the source language, edit only that paragraph (this is an explicit schema change requested by the owner) and add a line to `CUSTOMIZATIONS.md`.
5. **Team wiki destinations.** Ask whether there is a team wiki this wiki should be able to export to. If yes, add an entry under `share.destinations` in `wiki.config.json` (see `docs/customizing.md`) and note it in `CUSTOMIZATIONS.md`. If no, leave it empty; `wiki-share` stays inactive.
6. **Offer the first ingest.** The inbox contains `wiki/raw/inbox/2026-09-10-welcome-to-your-llm-wiki.md`. Offer to run `wiki-ingest` on it now.
7. **Report** what changed and point to `docs/onboarding.md` for the rest of the first day.

## Do not

- Create remote repositories, push, or change visibility; that is the owner's action.
- Edit any part of `wiki/CLAUDE.md` other than the language paragraph, and only when asked.
- Run the bootstrap on a copy that already has real pages without `--skip-tests` being considered; tests are quick, but say what you are running.
