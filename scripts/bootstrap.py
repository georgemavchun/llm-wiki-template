#!/usr/bin/env python3
"""Idempotent onboarding for a copy of llm-wiki-template.

Usage::

    python3 scripts/bootstrap.py [--owner "Name"] [--start-date YYYY-MM-DD]
        [--yes] [--skip-hooks] [--skip-tests] [--repo PATH]

Every step prints ``[done]``, ``[already]``, ``[skipped]`` or ``[failed]``
with a short label. Re-running is safe: placeholder replacement, directory
creation and the git hooks path are all checked before being changed.

Exit ``0`` when every mandatory step succeeded, ``1`` otherwise. Never
touches git history.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

PLACEHOLDER_FILES = ("wiki/CLAUDE.md", "wiki/LOG.md", "README.md", "CUSTOMIZATIONS.md")


def _load_config(repo_root: Path) -> dict:
    path = repo_root / "wiki.config.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _git_user_name(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "config", "user.name"], cwd=repo_root, capture_output=True, text=True
        )
    except Exception:
        return None
    name = result.stdout.strip()
    return name or None


def _parse_unittest_summary(text: str) -> str:
    ran_match = re.search(r"Ran (\d+) tests?", text)
    ran = int(ran_match.group(1)) if ran_match else 0
    if ran_match and "FAILED" not in text:
        return f"{ran} tests passed"
    fail_match = re.search(r"failures=(\d+)", text)
    error_match = re.search(r"errors=(\d+)", text)
    failures = int(fail_match.group(1)) if fail_match else 0
    errors = int(error_match.group(1)) if error_match else 0
    passed = max(ran - failures - errors, 0)
    return f"{passed}/{ran} tests passed ({failures} failed, {errors} errors)"


def step_python_version() -> tuple[str, str]:
    ok = sys.version_info >= (3, 9)
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if ok:
        return "done", f"python {version} (>= 3.9 required)"
    return "failed", f"python {version} is older than the required 3.9"


def step_git_repo(repo_root: Path) -> tuple[str, str, bool]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "skipped", "not a git repository", False
    if result.returncode == 0 and result.stdout.strip() == "true":
        return "done", "inside a git work tree", True
    return "skipped", "not a git repository", False


def step_placeholders(repo_root: Path, owner: str, start_date: str) -> tuple[str, str]:
    existing = [rel for rel in PLACEHOLDER_FILES if (repo_root / rel).exists()]
    touched = []
    for rel in existing:
        path = repo_root / rel
        text = path.read_text(encoding="utf-8")
        if "{{OWNER_NAME}}" in text or "{{START_DATE}}" in text:
            new_text = text.replace("{{OWNER_NAME}}", owner).replace("{{START_DATE}}", start_date)
            path.write_text(new_text, encoding="utf-8")
            touched.append(rel)
    if touched:
        return "done", f"replaced placeholders in {', '.join(touched)}"
    return "already", f"no placeholders remain in {', '.join(existing) if existing else '(no target files found)'}"


def step_hooks(repo_root: Path, is_git: bool, skip: bool) -> tuple[str, str]:
    if skip:
        return "skipped", "--skip-hooks"
    if not is_git:
        return "skipped", "not a git repository"

    hook_path = repo_root / "scripts" / "hooks" / "pre-commit"
    current = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"], cwd=repo_root, capture_output=True, text=True
    )
    already_set = current.returncode == 0 and current.stdout.strip() == "scripts/hooks"
    already_exec = hook_path.exists() and (hook_path.stat().st_mode & 0o111) == 0o111

    if already_set and already_exec:
        return "already", "core.hooksPath already scripts/hooks; pre-commit already executable"

    result = subprocess.run(
        ["git", "config", "core.hooksPath", "scripts/hooks"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "failed", f"git config core.hooksPath failed: {result.stderr.strip()}"

    if hook_path.exists():
        mode = hook_path.stat().st_mode
        hook_path.chmod(mode | 0o111)

    return "done", "core.hooksPath=scripts/hooks; pre-commit made executable"


def step_dirs(repo_root: Path, config: dict) -> tuple[str, str]:
    staging_name = (config.get("privacy") or {}).get("staging_dir") or ".staging"
    wiki_root_name = config.get("wiki_root", "wiki")
    staging_dir = repo_root / staging_name
    inbox_dir = repo_root / wiki_root_name / "raw" / "inbox"

    created = []
    already = []
    for directory, label in ((staging_dir, staging_name), (inbox_dir, f"{wiki_root_name}/raw/inbox")):
        if directory.exists():
            already.append(label)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            created.append(label)

    if created:
        suffix = f"; already present: {', '.join(already)}" if already else ""
        return "done", f"created {', '.join(created)}{suffix}"
    return "already", f"{', '.join(already)} already present"


def step_lint(repo_root: Path, wiki_root_name: str) -> tuple[str, str]:
    lint_script = repo_root / "scripts" / "wiki_lint.py"
    if not lint_script.exists():
        return "skipped", "scripts/wiki_lint.py not present yet"
    try:
        result = subprocess.run(
            [sys.executable, str(lint_script), "--wiki-root", wiki_root_name, "--brief"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return "skipped", f"could not run wiki_lint.py ({type(exc).__name__})"
    output = (result.stdout or result.stderr).strip()
    if output:
        print(output)
    return "done", "ran wiki_lint.py --brief"


def step_tests(repo_root: Path, skip: bool) -> tuple[str, str, bool]:
    if skip:
        return "skipped", "--skip-tests", True
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return "skipped", "no tests/ directory", True
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    summary = _parse_unittest_summary(result.stderr or result.stdout)
    ok = result.returncode == 0
    return ("done" if ok else "failed"), summary, ok


def print_next_steps() -> None:
    print("Next steps")
    print("  1. Open Claude Code here")
    print('  2. Say "ingest the inbox"')
    print('  3. Then "lint the wiki"')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Idempotent onboarding for a llm-wiki-template copy.")
    parser.add_argument("--owner", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--skip-hooks", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--repo", default=None)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo).resolve() if args.repo else Path.cwd()

    owner = args.owner
    if not owner:
        if sys.stdin.isatty() and not args.yes:
            try:
                owner = input("Owner name: ").strip()
            except (EOFError, KeyboardInterrupt):
                owner = ""
        if not owner:
            owner = _git_user_name(repo_root) or "Owner"

    start_date = args.start_date or date.today().isoformat()

    overall_ok = True

    status, msg = step_python_version()
    print(f"[{status}] python-version: {msg}")
    if status == "failed":
        overall_ok = False

    status, msg, is_git = step_git_repo(repo_root)
    print(f"[{status}] git-repo: {msg}")

    try:
        status, msg = step_placeholders(repo_root, owner, start_date)
    except Exception as exc:
        status, msg = "failed", f"{type(exc).__name__}: {exc}"
    print(f"[{status}] placeholders: {msg}")
    if status == "failed":
        overall_ok = False

    status, msg = step_hooks(repo_root, is_git, args.skip_hooks)
    print(f"[{status}] hooks: {msg}")
    if status == "failed":
        overall_ok = False

    config = _load_config(repo_root)
    try:
        status, msg = step_dirs(repo_root, config)
    except Exception as exc:
        status, msg = "failed", f"{type(exc).__name__}: {exc}"
    print(f"[{status}] dirs: {msg}")
    if status == "failed":
        overall_ok = False

    wiki_root_name = config.get("wiki_root", "wiki")
    status, msg = step_lint(repo_root, wiki_root_name)
    print(f"[{status}] lint: {msg}")

    status, msg, tests_ok = step_tests(repo_root, args.skip_tests)
    print(f"[{status}] tests: {msg}")
    if not tests_ok:
        overall_ok = False

    print()
    print_next_steps()

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
