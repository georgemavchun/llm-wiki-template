# Design

Why this template is built the way it is.

## The three-layer model

Every wiki here has three layers. **Raw** (`wiki/raw/`) is immutable source material: articles, transcripts, notes, exactly as they arrived. **Wiki** (`sources/`, `entities/`, `concepts/`, `synthesis/`) is what the agent writes: one page per source, one page per named thing, one page per idea, and occasionally a page that synthesizes several of those. **Schema** (`wiki/CLAUDE.md`) is the single document that tells the agent the conventions: where pages live, what frontmatter they carry, what to do on each operation.

The separation matters because each layer has a different owner and a different failure mode. Raw is the ground truth; if the agent could edit it, a paraphrase error would be indistinguishable from the original fact six months later. Wiki pages are meant to be rewritten and reorganized; treating them as immutable would make the wiki a pile of dated notes instead of a compounding artifact. The schema changes rarely and deliberately, because every other file's behavior depends on it staying stable.

## What this template adds beyond the pattern, and why

The pattern this template builds on describes raw sources, agent-written pages, an index and a log, and three operations: ingest, query, lint. That is enough for one person working alone with no downstream audience. Once a wiki might be shared, inspected by other people, or grow past a few dozen pages, gaps show up, and this template closes them:

- A privacy preflight before anything enters `wiki/raw/`, because a coding agent will happily transcribe whatever you paste, including a credential you did not mean to keep.
- A sensitivity vocabulary (`quarantine`, `personal`, `restricted`, `shareable`, plus `public` at the page level), because "should this leave my personal wiki" is a question every page eventually asks, and answering it consistently needs a shared vocabulary rather than a fresh judgment call each time.
- Immutable raw sources, enforced by hooks, not just documented as a convention, because a convention an agent can silently violate under time pressure is not a control.
- Deterministic lint separated from judgment, so "is this frontmatter valid" is answered by a script every time, and the agent's judgment is spent on genuinely hard questions like contradictions and weak links.
- Crystallize, a fourth operation alongside ingest, query and lint, because durable signal often comes from a conversation with the agent itself, not from an external document, and that signal needs the same discipline (placement, sourcing, dating) as an ingested source.
- Evolve, a meta-review of the system rather than the content, because a wiki's own conventions accumulate cruft the same way its content does, and reviewing them needs its own operation and its own approval gate.
- Share, a batch, owner-gated export path to a team or project wiki, and template-not-fork distribution, because both are about controlling what crosses a boundary. Share controls what leaves this wiki for another one; the template flag controls what a new copy starts with. A fork carries this repository's history forward; a template starts clean.

## Decisions and trade-offs

The template repository itself is created privately, with the template-repository flag enabled rather than left as an ordinary repository to fork. A copy can be made public later if its owner chooses, but a personal wiki has no reason to start that way.

The license is MIT: permissive enough that a colleague can adapt or redistribute a copy without asking, which matters for something meant to be copied many times inside and outside a company.

Wiki content lives under `wiki/`, with all tooling at the repository root, so that `wiki/` alone is a valid Obsidian vault, and the scripts, tests and skills that maintain it are not mixed into that vault.

Every script is Python 3.9 or newer, standard library only, with no `pip install` step. `gitleaks` is the one optional extra, auto-detected rather than required, because a template that needs a working package manager before its first run adds a failure point that has nothing to do with the wiki itself.

Four page families ship: `sources`, `entities`, `concepts`, `synthesis`. Others, such as decisions, projects, reflections or recipes, are documented as an extension point in [customizing.md](customizing.md) rather than shipped, because a family nobody uses is a family lint still has to account for.

The default language policy keeps wiki prose in English and raw sources verbatim in their original language, because cross-referencing works best when every page reads the same language, while a source loses meaning the moment it is silently translated. A wiki that will only ever be read by people fluent in one other language can flip this in one paragraph.

The sensitivity vocabulary has four classes rather than a longer list, because a longer list is harder to apply consistently under time pressure, and the four map cleanly onto a decision that matters: never store, never leave this wiki, leave only with per-item approval, or leave after normal review.

Team-wiki destinations are configuration, not code, and the list starts empty, so `wiki-share` is inert until it is deliberately pointed somewhere.

Meeting-recorder ingest ships adapter-agnostic with one worked example, a meeting-recorder MCP server named Jamie, because the discovery and paging mechanics are genuinely different per recorder, while the privacy and writing rules are not. Splitting them keeps the adapter short and the important rules in one place.

A classification ledger is required for transcripts and optional elsewhere, because transcripts carry the highest density of mixed personal and work content of anything the wiki ingests, while the deterministic preflight scan applies to every source regardless of type.

The inbox-drainer CI workflow ships disabled, manual-dispatch only, with an explicit warning about what running it unattended sends to the model provider, because turning an interactive, ask-before-writing tool into a scheduled job is a real change in what the tool does, not a convenience toggle.

Distribution is a standalone `.claude/skills/` directory rather than a packaged plugin, because that is what a template copied with git needs. Packaging is listed as a roadmap item below rather than built now, before real usage has tested which parts of the skill surface are worth packaging.

## Known limitations

The preflight scanner is a pattern matcher. It cannot see free-text sensitive content that carries no keyword it knows, such as a paragraph describing someone's health with no flagged term in it. Classification quality for anything past the deterministic subset depends on the agent applying the sensitivity taxonomy correctly, which is judgment, not a guarantee.

A wiki maintained by repeated summarization can drift: each re-summary is a chance to lose a qualifier or flatten a nuance. The mitigation here is structural, not a promise: surgical edits (change the section that changed, never rewrite a whole page) and keeping the source page as the place a faithful, less-compressed account lives, so a drifted downstream page can always be checked against it.

There are no typed links between pages (every link is a plain `[[slug]]`, with no relationship type) and no vector search; `wiki_search.py` is keyword-based (BM25). Both are plausible additions once a wiki is large enough that an index and keyword search stop being sufficient, which the pattern this template builds on estimates at a few hundred pages.

## Roadmap

Plugin or marketplace packaging of the skill set. Per-page content hashes, so lint could detect a page changed outside the tools meant to change it. Log rotation, once `wiki/LOG.md` itself grows large enough to be worth splitting by date range.

## Credits

The three-layer model, the ingest, query and lint operations, and the index-plus-log convention are Andrej Karpathy's, from his [LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) (2026-04-04). The privacy and integrity layer around that pattern draws on the author's personal and corporate wikis, and on several independent open-source explorations of the same idea, credited here for the specific idea each one contributed:

- [AgriciDaniel/claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian): approval-before-write and a checksummed audit trail informed how this template's write guard and log format think about accountability.
- [praneybehl/llm-wiki-plugin](https://github.com/praneybehl/llm-wiki-plugin): the separation between deterministic lint and LLM judgment, carried directly into `wiki_lint.py` versus the judgment-checks section of the lint skill.
- [eugeniughelbur/obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain): a fork-delta file and "as of" dating for time-bound facts, which became `CUSTOMIZATIONS.md` and the schema's dating convention.
- [vanillaflava/llm-wiki-skills](https://github.com/vanillaflava/llm-wiki-skills): the crystallize operation, and the practice of stating plainly that everything under the wiki root is sent to the model provider.
- [Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki): writing explicit non-goals down, which shaped the "Known limitations" section above and the out-of-scope items kept as a roadmap.

Also: the [Claude Code hooks](https://code.claude.com/docs/en/hooks.md), [skills](https://code.claude.com/docs/en/skills.md) and [memory](https://code.claude.com/docs/en/memory.md) documentation; the [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/), for the prompt-injection framing behind the untrusted-sources rules; and [gitleaks](https://github.com/gitleaks/gitleaks), the optional secret scanner the pre-commit hook picks up automatically.
