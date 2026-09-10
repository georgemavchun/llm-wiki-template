# Customizing this template

Everything here changes how your copy behaves. Record every change in [../CUSTOMIZATIONS.md](../CUSTOMIZATIONS.md) as you make it. That file tells you, and the agent, what to re-apply when a newer template version arrives.

## Language policy

The language policy lives as one paragraph in [../wiki/CLAUDE.md](../wiki/CLAUDE.md), under "Language policy". The default keeps wiki pages in English and raw sources verbatim in their original language. If you want pages written in the source's own language instead, edit only that paragraph; this is an explicit schema change, so the agent will not do it without you asking, and `wiki-setup` asks about it once during first-time setup. Add a line to `CUSTOMIZATIONS.md` when you change it.

## Adding a page family

The shipped families are `sources`, `entities`, `concepts`, `synthesis`. To add one, for example `decisions`:

1. Add an entry to `wiki.config.json → page_families`, mapping the directory name to a `page_type` value: `"decisions": "decision"`.
2. Create the directory `wiki/decisions/`.
3. Add a template at `wiki/_templates/decision.md` with the required frontmatter keys (`title`, `page_type`, `reliability`, `sensitivity`, `sources`, `created`, `updated`, `tags`) and `page_type: decision` set.
4. Add a `## Decisions` heading to `wiki/INDEX.md`, or the matching `INDEX-decisions.md` shard once you shard.
5. `scripts/new_page.py decisions <slug> --title "..."` and `scripts/wiki_lint.py` both pick up the new family automatically once the config and template exist; nothing else needs code changes.

## Privacy allowlist location

`privacy.allowlist` in `wiki.config.json` names the file that records owner-approved scanner false positives (default `wiki/privacy-allowlist.json`). It is created on demand; keep it under version control so the pre-commit hook and CI see the same decisions.

## Changing caps and staleness

`wiki.config.json → caps.soft_lines` and `caps.hard_lines` set the page-size thresholds lint watches. `staleness_days` sets how old a `reliability: low` page, a `## Pending Review` section, or an untouched page (`cold_page`) has to be before lint warns about it. Lower `hard_lines` if you want pages split earlier; raise `staleness_days.cold_page` if your wiki is used in bursts rather than continuously.

## Adding a share destination

By default `wiki.config.json → share.destinations` is empty and `wiki-share` is inactive. Add a destination:

```json
{
  "share": {
    "destinations": {
      "team": {
        "path": "../team-wiki",
        "raw_dir": "raw/inbox",
        "language": "en",
        "filename_style": "kebab"
      }
    }
  }
}
```

- `path`: where the destination repository lives, relative to this one.
- `raw_dir`: where `wiki-share` drops extract files inside it, matching that wiki's own inbox convention.
- `language`: the language extracts are translated into, if it differs from this wiki's.
- `filename_style`: how `wiki-share` names files it writes (`kebab` is the only style shipped; document any other style you add here).

Once a destination exists, `wiki-share` reads its own schema (its `CLAUDE.md` or `README.md`) for naming and frontmatter conventions, classifies candidates against the sensitivity taxonomy, and asks you, item by item and destination by destination, before writing anything.

## Writing a meeting-recorder adapter

`wiki-ingest-meetings` is recorder-agnostic; the recorder-specific mechanics live in one file under `.claude/skills/wiki-ingest-meetings/references/adapters/`. The shipped adapter, [../.claude/skills/wiki-ingest-meetings/references/adapters/jamie.md](../.claude/skills/wiki-ingest-meetings/references/adapters/jamie.md), is the pattern to copy. An adapter needs to answer three questions in under 20 lines:

- **Discovery**: how to list candidate recordings, and how to tell which ones are already ingested (a tag, a label, a moved file, whatever survives a re-run).
- **Full transcript retrieval**: the recorder's summary is usually truncated; how do you page through to the complete transcript, and how big are the pages?
- **Markers**: what tag or label means "ingested" and what means "skipped" (misfires, deliberate exclusions), and how do you apply one to a batch of recordings?

Everything else, the privacy scan, the ledger, writing pages, is `wiki-ingest`'s job, unchanged.

## Adding a skill of your own

A skill is one `SKILL.md` file under `.claude/skills/<name>/`. Keep the frontmatter portable: only `name` (matching the directory) and `description` (starting with "Use when", naming its trigger phrases). Keep the body under 250 lines; move anything heavier into a `references/` subdirectory and link to it from the body. Refer to scripts by their path (`scripts/your_script.py`) so the contract tests can confirm they exist. Add a line to [../CUSTOMIZATIONS.md](../CUSTOMIZATIONS.md) once it works.

## Adjusting permissions

Shared permissions and hooks live in `.claude/settings.json` and apply to everyone who opens this repository with Claude Code. Personal overrides, such as a permission only you want or a different default model, go in `.claude/settings.local.json`, which is already in `.gitignore` and never committed. Do not loosen `deny: ["Edit(./wiki/raw/**)"]` in the shared file. If you genuinely need to bypass it once, use the documented redaction procedure in [privacy.md](privacy.md) instead.

## Enabling the inbox-drainer workflow

`.github/workflows/inbox-drainer.yml` ships as manual-dispatch only, with its `schedule:` trigger commented out. Before enabling a schedule, read the warning at the top of that file: everything under the repository, including every file waiting in the inbox, is sent to the model provider from GitHub's infrastructure when this workflow runs, and the interactive "ask the owner" step that ingest normally uses cannot happen in an unattended run. Only turn on the schedule if every source that could land in your inbox is something you are comfortable being processed unattended.

## Sharding the index

Around 150 pages, `wiki/INDEX.md` gets long enough that reading it in full stops being cheap. Split it by page type into `INDEX-sources.md`, `INDEX-entities.md`, `INDEX-concepts.md`, `INDEX-synthesis.md`, and turn `INDEX.md` itself into a short hub linking to each shard. `wiki_lint.py` accepts either layout, so you can shard on your own schedule rather than all at once.

## Recording changes

Every deliberate deviation from the upstream template, however small, gets one line in [../CUSTOMIZATIONS.md](../CUSTOMIZATIONS.md): the date, the area, what changed, and why. This is what makes an upgrade (below) a merge instead of a guess.

## Upgrading from a newer template version

1. Copy the new `scripts/`, `.claude/`, and `tests/` directories over your own.
2. Merge `wiki/CLAUDE.md` by hand: use [../CUSTOMIZATIONS.md](../CUSTOMIZATIONS.md) to see what you changed locally and re-apply it on top of the new schema.
3. Run `python3 -m unittest discover -s tests -v` and `python3 scripts/wiki_lint.py --wiki-root wiki`; fix anything that breaks before you keep working.
4. Check [../CHANGELOG.md](../CHANGELOG.md) for what changed upstream and whether any of it needs a matching change to your own content.
