from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "bootstrap.py"

PLACEHOLDER_FILES = ("wiki/CLAUDE.md", "wiki/LOG.md", "README.md", "CUSTOMIZATIONS.md")


def _copy_template(dest: Path) -> None:
    for item in REPO_ROOT.iterdir():
        if item.name in (".git", "__pycache__"):
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(
                item, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
        else:
            shutil.copy(item, target)


def _run(args, cwd: Path, stdin_text: str = ""):
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        cwd=str(cwd),
        input=stdin_text,
        capture_output=True,
        text=True,
    )


class BootstrapGitRepoTests(unittest.TestCase):
    """Bootstrap against a fresh copy of the shipped template, inside a git repo."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        _copy_template(self.root)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "t@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Ada Lovelace"], check=True)

    def _run(self, extra_args=()):
        args = ["--owner", "Ada Lovelace", "--start-date", "2026-01-01", "--yes", "--skip-tests"]
        args += list(extra_args)
        return _run(args, self.root)

    def test_first_run_replaces_all_placeholders(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[done] placeholders", result.stdout)
        for rel in PLACEHOLDER_FILES:
            path = self.root / rel
            if path.exists():
                self.assertNotIn("{{", path.read_text(encoding="utf-8"), rel)

    def test_second_run_reports_already_for_placeholders(self):
        first = self._run()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = self._run()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("[already] placeholders", second.stdout)

    def test_hooks_are_installed_and_idempotent(self):
        first = self._run()
        self.assertIn("[done] hooks", first.stdout)
        hooks_path = subprocess.run(
            ["git", "-C", str(self.root), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(hooks_path, "scripts/hooks")
        pre_commit = self.root / "scripts" / "hooks" / "pre-commit"
        self.assertTrue(pre_commit.exists())
        import os

        self.assertTrue(os.access(pre_commit, os.X_OK))

        second = self._run()
        self.assertIn("[already] hooks", second.stdout)

    def test_skip_hooks_flag_skips_hook_step(self):
        result = self._run(extra_args=["--skip-hooks"])
        self.assertIn("[skipped] hooks", result.stdout)

    def test_creates_staging_and_inbox_dirs(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.root / ".staging").is_dir())
        self.assertTrue((self.root / "wiki" / "raw" / "inbox").is_dir())

    def test_dirs_step_idempotent(self):
        self._run()
        second = self._run()
        self.assertIn("[already] dirs", second.stdout)

    def test_prints_next_steps(self):
        result = self._run()
        self.assertIn("Next steps", result.stdout)
        self.assertIn("ingest the inbox", result.stdout)
        self.assertIn("lint the wiki", result.stdout)

    def test_never_creates_a_commit(self):
        self._run()
        log = subprocess.run(
            ["git", "-C", str(self.root), "log", "--oneline"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(log.stdout.strip(), "")


class BootstrapTestsStepTests(unittest.TestCase):
    """Exercise step 7 (running the test suite) in isolation.

    Deliberately does NOT copy the real repository's tests/ directory: that
    directory contains this very test file, and running bootstrap without
    --skip-tests against a full template copy would recursively re-run the
    whole suite (which itself would recurse again), so this fixture ships
    only scripts/bootstrap.py plus a tiny, self-contained tests/ package.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        (self.root / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.root / "scripts" / "bootstrap.py")
        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        (tests_dir / "__init__.py").write_text("", encoding="utf-8")
        (tests_dir / "test_trivial.py").write_text(
            "import unittest\n\n"
            "class TrivialTests(unittest.TestCase):\n"
            "    def test_passes(self):\n"
            "        self.assertEqual(1 + 1, 2)\n",
            encoding="utf-8",
        )

    def test_runs_test_suite_and_reports_pass_count(self):
        result = _run(
            ["--owner", "X", "--start-date", "2026-01-01", "--yes", "--skip-hooks"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[done] tests:", result.stdout)
        self.assertIn("1 tests passed", result.stdout)

    def test_skip_tests_flag_skips_the_step(self):
        result = _run(
            ["--owner", "X", "--start-date", "2026-01-01", "--yes", "--skip-hooks", "--skip-tests"],
            self.root,
        )
        self.assertIn("[skipped] tests: --skip-tests", result.stdout)

    def test_missing_tests_directory_is_skipped_not_failed(self):
        shutil.rmtree(self.root / "tests")
        result = _run(
            ["--owner", "X", "--start-date", "2026-01-01", "--yes", "--skip-hooks"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[skipped] tests:", result.stdout)


class BootstrapNonGitTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        _copy_template(self.root)

    def test_reports_skipped_git_and_hooks_but_still_succeeds(self):
        result = _run(
            ["--owner", "Someone", "--start-date", "2026-01-01", "--yes", "--skip-tests"],
            self.root,
        )
        self.assertIn("[skipped] git-repo: not a git repository", result.stdout)
        self.assertIn("[skipped] hooks: not a git repository", result.stdout)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class BootstrapOwnerResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        _copy_template(self.root)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "t@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Grace Hopper"], check=True)

    def test_falls_back_to_git_user_name_when_owner_omitted_noninteractive(self):
        result = _run(["--start-date", "2026-01-01", "--yes", "--skip-tests"], self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = (self.root / "wiki" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("Grace Hopper", text)


class BootstrapRepoFlagTests(unittest.TestCase):
    def test_repo_flag_targets_other_directory(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        _copy_template(root)
        subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "t@example.com"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Repo Flag"], check=True)

        elsewhere = tempfile.TemporaryDirectory()
        self.addCleanup(elsewhere.cleanup)

        result = _run(
            ["--owner", "Repo Flag", "--start-date", "2026-01-01", "--yes", "--skip-tests", "--repo", str(root)],
            Path(elsewhere.name),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = (root / "wiki" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("{{OWNER_NAME}}", text)


if __name__ == "__main__":
    unittest.main()
