# llm-wiki-template

A GitHub template for a personal, git-tracked, markdown knowledge base that a coding agent maintains for you. You keep git and markdown; the agent does the filing, cross-linking and consistency work described in Andrej Karpathy's LLM Wiki pattern. This template adds a privacy scanner, a sensitivity vocabulary, immutable raw sources and a deterministic health check on top of that pattern, so the wiki stays useful and safe to keep in git.

This copy: {{OWNER_NAME}}, started {{START_DATE}}. Placeholders like these are filled in automatically by `scripts/bootstrap.py` in step 3 below.

## Start here

1. On GitHub, click **Use this template**, not **Fork**. A fork keeps this template's git history; using the template starts your copy with a clean history of its own.
2. Clone your new repository and open a terminal in it.
3. Run the bootstrap script:

   ```bash
   python3 scripts/bootstrap.py --owner "Your Name"
   ```

4. Open Claude Code in the folder and say:

   ```
   ingest the inbox
   ```

5. Ask a question:

   ```
   what does the wiki say about the LLM wiki pattern
   ```

6. Check the wiki's health:

   ```
   lint the wiki
   ```

7. Commit:

   ```bash
   git add -A
   git commit -m "ingest: welcome tutorial"
   ```

For the full first-hour walkthrough, including what to expect at each step, see [docs/onboarding.md](docs/onboarding.md).

## Prerequisites

- git
- Python 3.9 or newer
- Claude Code

Optional: Obsidian, for browsing the wiki as a linked graph. Optional: gitleaks, as an extra secret-scanning layer on top of the built-in scanner.

## Repository layout

```
llm-wiki-template/
├── README.md  LICENSE  CHANGELOG.md  CONTRIBUTING.md  SECURITY.md  CUSTOMIZATIONS.md
├── CLAUDE.md                 agent guide, imports wiki/CLAUDE.md
├── AGENTS.md                 pointer for non-Claude agents
├── wiki.config.json          page families, caps, privacy settings, share destinations
├── .gitignore  .editorconfig
├── .claude/
│   ├── settings.json         permissions and hooks
│   ├── rules/raw-immutability.md
│   ├── agents/wiki-scout.md
│   └── skills/
│       ├── wiki-setup/  wiki-ingest/  wiki-ingest-light/
│       ├── wiki-ingest-meetings/  (references/adapters/jamie.md)
│       ├── wiki-crystallize/  wiki-query/  wiki-lint/
│       └── wiki-evolve/  wiki-share/  (references/sensitivity-taxonomy.md)
├── scripts/
│   ├── wiki_lint.py  wiki_search.py  new_page.py  bootstrap.py
│   ├── privacy_preflight.py  validate_privacy_ledger.py
│   └── hooks/  pre-commit  guard_write.py  session_start.py
├── tests/                    unittest, standard library only
├── docs/                     onboarding, privacy, skills, customizing, design, faq
├── .github/workflows/        checks.yml  inbox-drainer.yml
└── wiki/
    ├── CLAUDE.md  README.md  INDEX.md  LOG.md
    ├── _templates/           source.md  entity.md  concept.md  synthesis.md
    ├── raw/inbox/            tutorial source
    └── sources/  entities/  concepts/  synthesis/
```

## Skills

Say any of these once Claude Code is open in the repository. Full detail, including what each skill never does, is in [docs/skills.md](docs/skills.md).

| Skill | Say it like this | What it writes |
|---|---|---|
| `wiki-setup` | "set up my wiki" | placeholders filled, git hooks installed |
| `wiki-ingest` | "ingest the inbox", "add this source" | a source page, entity and concept edits, index, log |
| `wiki-ingest-light` | "quick note: ..." | a raw fragment, surgical edits to existing pages, log |
| `wiki-ingest-meetings` | "pull new meetings" | staged transcripts handed to `wiki-ingest`, recorder tags |
| `wiki-crystallize` | "crystallize this" | concept or synthesis edits drawn from a conversation, log |
| `wiki-query` | "what does the wiki say about X" | an answer with citations; a synthesis page only if you agree |
| `wiki-lint` | "lint the wiki" | a report only, plus one log line |
| `wiki-evolve` | "evolve the wiki" | proposals for the schema and templates, applied only with your approval |
| `wiki-share` | "share this with the team wiki" | sanitized extracts to a configured destination |

## Privacy, in five lines

Everything the agent reads under this repository is sent to the model provider. Keep this wiki in its own repository, away from anything that must not leave your machine. Nothing enters `wiki/raw/` without passing a deterministic scanner first. Raw sources cannot be edited or deleted through Claude Code once placed, and a git hook enforces the same rule at commit time. The full model, including the sensitivity classes and what to do if something slips through, is in [docs/privacy.md](docs/privacy.md).

## Documentation

- [docs/onboarding.md](docs/onboarding.md): first hour, step by step
- [docs/privacy.md](docs/privacy.md): the privacy and integrity model
- [docs/skills.md](docs/skills.md): every skill and script in detail
- [docs/customizing.md](docs/customizing.md): adapting the template to your own wiki
- [docs/design.md](docs/design.md): why the template is built this way
- [docs/faq.md](docs/faq.md): short answers to common questions

Not using Claude Code? Start from [AGENTS.md](AGENTS.md) instead.

## Upgrading a copy

When a newer template version is released, [CUSTOMIZATIONS.md](CUSTOMIZATIONS.md) records what you changed in your copy, so you know what to re-apply and what to leave alone. See [CHANGELOG.md](CHANGELOG.md) for what changed upstream.

## License

MIT. See [LICENSE](LICENSE).

## Credit

The three-layer wiki, the ingest, query and lint operations, and the index-plus-log convention come from Andrej Karpathy's [LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) (2026-04-04). This template adds the privacy and integrity layer around that pattern; see [docs/design.md](docs/design.md) for what and why.
