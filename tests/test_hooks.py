from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_WRITE = REPO_ROOT / "scripts" / "hooks" / "guard_write.py"
SESSION_START = REPO_ROOT / "scripts" / "hooks" / "session_start.py"
PRE_COMMIT = REPO_ROOT / "scripts" / "hooks" / "pre-commit"

GIT_ENV_EXTRA = {
    "GIT_AUTHOR_NAME": "Test User",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test User",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _git_env(base: dict) -> dict:
    env = dict(base)
    env.update(GIT_ENV_EXTRA)
    return env


def _copy_template_scripts(dest: Path) -> None:
    """Copy wiki.config.json, scripts/ and a minimal wiki/ into dest."""
    shutil.copy(REPO_ROOT / "wiki.config.json", dest / "wiki.config.json")
    shutil.copytree(REPO_ROOT / "scripts", dest / "scripts")
    (dest / "wiki" / "raw" / "inbox").mkdir(parents=True, exist_ok=True)
    (dest / "wiki" / "entities").mkdir(parents=True, exist_ok=True)
    (dest / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
    (dest / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
    (dest / "wiki" / "synthesis").mkdir(parents=True, exist_ok=True)
    (dest / "wiki" / "_templates").mkdir(parents=True, exist_ok=True)
    for name in ("source.md", "entity.md", "concept.md", "synthesis.md"):
        src = REPO_ROOT / "wiki" / "_templates" / name
        if src.exists():
            shutil.copy(src, dest / "wiki" / "_templates" / name)


def _run_guard_write(payload: dict, project_dir: Path):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return subprocess.run(
        [sys.executable, str(project_dir / "scripts" / "hooks" / "guard_write.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


class GuardWriteTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.project_dir = Path(self.tempdir.name)
        _copy_template_scripts(self.project_dir)

    def _payload(self, tool_name: str, tool_input: dict) -> dict:
        return {
            "session_id": "s1",
            "cwd": str(self.project_dir),
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_use_id": "t1",
        }

    def test_write_into_raw_is_blocked(self):
        payload = self._payload("Write", {"file_path": "wiki/raw/x.md", "content": "hello"})
        result = _run_guard_write(payload, self.project_dir)
        self.assertEqual(result.returncode, 2)
        self.assertIn("add-only", result.stderr)

    def test_write_into_raw_inbox_is_blocked(self):
        payload = self._payload("Write", {"file_path": "wiki/raw/inbox/x.md", "content": "hello"})
        result = _run_guard_write(payload, self.project_dir)
        self.assertEqual(result.returncode, 2)
        self.assertIn("add-only", result.stderr)

    def test_clean_edit_outside_raw_is_allowed(self):
        payload = self._payload(
            "Edit",
            {
                "file_path": "wiki/entities/x.md",
                "old_string": "old",
                "new_string": "clean, unremarkable text",
            },
        )
        result = _run_guard_write(payload, self.project_dir)
        self.assertEqual(result.returncode, 0)

    def test_write_with_secret_is_blocked_and_value_not_echoed(self):
        secret = "AKIA" + "ABCDEFGH12345678"
        payload = self._payload(
            "Write", {"file_path": "wiki/entities/x.md", "content": f"key: {secret}"}
        )
        result = _run_guard_write(payload, self.project_dir)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(secret, result.stdout)
        self.assertNotIn(secret, result.stderr)

    def test_multiedit_with_private_key_is_blocked(self):
        payload = self._payload(
            "MultiEdit",
            {
                "file_path": "wiki/entities/x.md",
                "edits": [
                    {"old_string": "a", "new_string": "clean"},
                    {
                        "old_string": "b",
                        "new_string": "-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----",
                    },
                ],
            },
        )
        result = _run_guard_write(payload, self.project_dir)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("MIIB", result.stdout)

    def _write_allowlist(self, entries: list) -> None:
        allowlist_path = self.project_dir / "wiki" / "privacy-allowlist.json"
        allowlist_path.parent.mkdir(parents=True, exist_ok=True)
        allowlist_path.write_text(
            json.dumps({"schema_version": 1, "entries": entries}), encoding="utf-8"
        )

    def test_write_matching_allowlisted_path_and_sha_is_allowed(self):
        content = "This is off the record.\n"
        self._write_allowlist(
            [
                {
                    "path": "wiki/entities/allowed.md",
                    "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "reason_codes": ["explicit-no-record-en"],
                    "approved_by": "Owner Name",
                    "date": "2026-09-10",
                }
            ]
        )
        payload = self._payload("Write", {"file_path": "wiki/entities/allowed.md", "content": content})
        result = _run_guard_write(payload, self.project_dir)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_write_with_unlisted_finding_alongside_allowlisted_one_is_blocked(self):
        content = "This is off the record.\nPassword: correcthorsebattery\n"
        self._write_allowlist(
            [
                {
                    "path": "wiki/entities/allowed2.md",
                    "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "reason_codes": ["explicit-no-record-en"],
                    "approved_by": "Owner Name",
                    "date": "2026-09-10",
                }
            ]
        )
        payload = self._payload("Write", {"file_path": "wiki/entities/allowed2.md", "content": content})
        result = _run_guard_write(payload, self.project_dir)
        self.assertEqual(result.returncode, 2)
        self.assertIn("labelled-secret", result.stderr)
        self.assertNotIn("explicit-no-record", result.stderr)
        self.assertNotIn("correcthorsebattery", result.stdout)
        self.assertNotIn("correcthorsebattery", result.stderr)

    def test_write_with_different_content_at_allowlisted_path_is_still_blocked(self):
        allowlisted_content = "This is off the record.\n"
        self._write_allowlist(
            [
                {
                    "path": "wiki/entities/allowed3.md",
                    "sha256": hashlib.sha256(allowlisted_content.encode("utf-8")).hexdigest(),
                    "reason_codes": ["explicit-no-record-en"],
                    "approved_by": "Owner Name",
                    "date": "2026-09-10",
                }
            ]
        )
        different_content = "This is off the record too.\n"
        payload = self._payload(
            "Write", {"file_path": "wiki/entities/allowed3.md", "content": different_content}
        )
        result = _run_guard_write(payload, self.project_dir)
        self.assertEqual(result.returncode, 2)

    def test_unrelated_tool_is_allowed(self):
        payload = self._payload("Bash", {"command": "ls"})
        result = _run_guard_write(payload, self.project_dir)
        self.assertEqual(result.returncode, 0)

    def test_malformed_json_exits_one(self):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project_dir)
        result = subprocess.run(
            [sys.executable, str(self.project_dir / "scripts" / "hooks" / "guard_write.py")],
            input="not valid json{{{",
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 1)


class SessionStartTests(unittest.TestCase):
    def test_prints_reminder_and_stays_short(self):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(REPO_ROOT)
        result = subprocess.run(
            [sys.executable, str(SESSION_START)],
            input=json.dumps({"session_id": "s1", "hook_event_name": "SessionStart", "source": "startup"}),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertLessEqual(len(lines), 5)
        self.assertIn("Read wiki/CLAUDE.md", result.stdout)

    def test_ignores_stdin_content_gracefully(self):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(REPO_ROOT)
        result = subprocess.run(
            [sys.executable, str(SESSION_START)],
            input="not json at all",
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Read wiki/CLAUDE.md", result.stdout)


@unittest.skipUnless(shutil.which("git"), "git not available")
class PreCommitTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.repo = Path(self.tempdir.name)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test User"], check=True)

        _copy_template_scripts(self.repo)
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "core.hooksPath", "scripts/hooks"], check=True
        )
        os.chmod(self.repo / "scripts" / "hooks" / "pre-commit", 0o755)

    def _git(self, *args, env=None, check=False):
        full_env = _git_env(dict(os.environ))
        if env:
            full_env.update(env)
        return subprocess.run(
            ["git", "-C", str(self.repo)] + list(args),
            capture_output=True,
            text=True,
            env=full_env,
            check=check,
        )

    def _write_page(self, rel_path: str, extra_body: str = "Nothing sensitive here.") -> Path:
        path = self.repo / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            'title: "Test Page"\n'
            "page_type: entity\n"
            "reliability: medium\n"
            "sensitivity: personal\n"
            'sources: ["sources/x.md"]\n'
            "created: 2026-01-01\n"
            "updated: 2026-01-01\n"
            "tags: []\n"
            "---\n\n"
            "# Test Page\n\n"
            f"{extra_body}\n",
            encoding="utf-8",
        )
        return path

    def test_committing_clean_page_succeeds(self):
        self._write_page("wiki/entities/clean.md")
        self._git("add", "wiki/entities/clean.md", check=True)
        result = self._git("commit", "-m", "add clean page")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_committing_staging_area_fails(self):
        staging = self.repo / ".staging" / "draft.md"
        staging.parent.mkdir(parents=True, exist_ok=True)
        staging.write_text("draft content\n", encoding="utf-8")
        self._git("add", "-f", ".staging/draft.md", check=True)
        result = self._git("commit", "-m", "add staging")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".staging/", result.stdout + result.stderr)

    def test_modifying_committed_raw_file_requires_override(self):
        raw = self.repo / "wiki" / "raw" / "a.md"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("original raw content\n", encoding="utf-8")
        self._git("add", "wiki/raw/a.md", check=True)
        self._git("commit", "-m", "add raw a.md", check=True)

        raw.write_text("modified raw content\n", encoding="utf-8")
        self._git("add", "wiki/raw/a.md", check=True)

        blocked = self._git("commit", "-m", "modify raw without override")
        self.assertNotEqual(blocked.returncode, 0)

        allowed = self._git("commit", "-m", "modify raw with override", env={"WIKI_ALLOW_RAW_CHANGE": "1"})
        self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_inbox_is_a_drop_zone_and_the_move_into_raw_is_allowed(self):
        inbox = self.repo / "wiki" / "raw" / "inbox" / "note.md"
        inbox.parent.mkdir(parents=True, exist_ok=True)
        inbox.write_text("dropped source\n", encoding="utf-8")
        self._git("add", "wiki/raw/inbox/note.md", check=True)
        self._git("commit", "-m", "drop a source into the inbox", check=True)

        # The owner may still edit or remove an inbox file without any override.
        inbox.write_text("dropped source, corrected by the owner\n", encoding="utf-8")
        self._git("add", "wiki/raw/inbox/note.md", check=True)
        edited = self._git("commit", "-m", "fix inbox file")
        self.assertEqual(edited.returncode, 0, edited.stderr)

        # The documented ingest step (mv inbox -> raw) is a rename in git terms.
        target = self.repo / "wiki" / "raw" / "note.md"
        inbox.rename(target)
        self._git("add", "-A", "wiki/raw", check=True)
        moved = self._git("commit", "-m", "ingest: move note into raw")
        self.assertEqual(moved.returncode, 0, moved.stderr)

        # Once outside the inbox, a rename is a change to a cleared source.
        target.rename(self.repo / "wiki" / "raw" / "renamed.md")
        self._git("add", "-A", "wiki/raw", check=True)
        renamed = self._git("commit", "-m", "rename a cleared source")
        self.assertNotEqual(renamed.returncode, 0)
        self.assertIn("add-only", renamed.stdout + renamed.stderr)

    @unittest.skipUnless(
        (REPO_ROOT / "scripts" / "privacy_preflight.py").exists(),
        "scripts/privacy_preflight.py not present yet",
    )
    def test_committing_secret_fails_without_leaking_it(self):
        secret = "AKIA" + "ABCDEFGH12345678"
        self._write_page("wiki/entities/secret.md", extra_body=f"aws_key: {secret}")
        self._git("add", "wiki/entities/secret.md", check=True)
        result = self._git("commit", "-m", "add secret page")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(secret, result.stdout)
        self.assertNotIn(secret, result.stderr)


if __name__ == "__main__":
    unittest.main()
