# Security and privacy

This template exists to keep a personal knowledge base out of trouble. The short version:

- **Never commit** credentials, government or tax identifiers, card or account numbers, health or compensation details about identifiable people, privileged legal material, or anything said off the record. The schema in `wiki/CLAUDE.md` lists the quarantine tier; `scripts/privacy_preflight.py`, the git pre-commit hook and the Claude Code write guard enforce the deterministic part.
- **Everything the agent reads is sent to the model provider.** Keep the wiki in its own repository, away from directories that hold secrets or unrelated sensitive files.
- **Git history is forever** unless rewritten. If something sensitive was committed, follow `docs/privacy.md` § "If a secret got in" before pushing anything else.
- **Start colleagues from the template, not from a fork.** A fork inherits history; "Use this template" starts clean.

## Reporting a problem with the template

If you find a way for the template's tooling to leak, echo or store sensitive values, or a bypass of the raw-immutability or preflight controls, open a private security advisory on the template repository or contact the maintainer directly rather than filing a public issue. Include the file and a reproduction that uses invented data only.

## What the tooling guarantees, and what it does not

Guaranteed by tests: the scanner and hooks never print a matched value; raw files cannot be edited through Claude Code's file tools; modified raw files cannot be committed without an explicit override; the shipped template contains no personal data.

Not guaranteed: detection of free-text sensitive content (a paragraph about someone's health with no keyword the scanner knows), classification quality (that is the agent's judgment under the taxonomy), or protection against an operator who bypasses hooks deliberately. Treat the tooling as a seatbelt, not a vault.
