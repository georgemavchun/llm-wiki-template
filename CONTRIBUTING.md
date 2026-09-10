# Contributing to the template

This file is about improving `llm-wiki-template` itself. If you are using a copy of it as your wiki, you do not need it; record your local changes in `CUSTOMIZATIONS.md` instead.

## Ground rules

- **No personal data, ever.** Test fixtures use invented names and values. The contract tests scan the repository for a denylist of real names and paths and fail on a match.
- **Standard library only.** Every script runs on Python 3.9+ with no third-party packages. The pre-commit hook is POSIX `sh`.
- **Deterministic before judgment.** If a check can be done mechanically, put it in a script with a test, not in a skill's prose.
- **Skills stay portable.** `SKILL.md` frontmatter uses only `name` and `description`; the body stays under ~250 lines; heavy reference goes in `references/`.
- **Schema changes are deliberate.** `wiki/CLAUDE.md` is the contract every copy inherits; change it in its own commit with a `CHANGELOG.md` entry.

## Workflow

1. Create a branch.
2. Make the change with tests: `python3 -m unittest discover -s tests -v` must pass, and `python3 scripts/wiki_lint.py --wiki-root wiki` must report zero errors.
3. If you touched a skill, exercise it once in a scratch copy of the template with Claude Code and note what you observed in the pull request.
4. Add a line to `CHANGELOG.md` under "Unreleased".
5. Open a pull request. CI runs the same checks.

## Releasing a template version

Bump the version in `CHANGELOG.md`, tag `vX.Y.Z`, and describe in the release notes what a copy needs to do to upgrade (usually: copy `scripts/`, `.claude/`, `tests/` and merge `wiki/CLAUDE.md` by hand, guided by `CUSTOMIZATIONS.md`).
