from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "new_page.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _make_wiki_copy(root: Path) -> None:
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / "wiki" / "_templates", root / "wiki" / "_templates")
    for family in ("sources", "entities", "concepts", "synthesis"):
        (root / "wiki" / family).mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / "wiki.config.json", root / "wiki.config.json")


def _run(args, cwd: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


class NewPageCliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        _make_wiki_copy(self.root)

    def test_creates_entity_page(self):
        result = _run(
            ["entities", "test-entity", "--title", "Test Entity", "--today", "2026-09-10"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.root / "wiki" / "entities" / "test-entity.md"
        self.assertTrue(target.exists())
        text = target.read_text(encoding="utf-8")
        self.assertIn('title: "Test Entity"', text)
        self.assertIn("# Test Entity", text)
        self.assertIn("page_type: entity", text)
        self.assertIn("created: 2026-09-10", text)
        self.assertIn("updated: 2026-09-10", text)
        # Compare resolved paths: on macOS the script's Path.cwd() may report
        # the /private-prefixed real path for a tempdir under a /var symlink.
        self.assertEqual(Path(result.stdout.strip()).resolve(), target.resolve())

    def test_creates_source_page_with_title_and_heading_placeholders(self):
        result = _run(
            ["sources", "gist-note", "--title", "Gist Note", "--today", "2026-09-10"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.root / "wiki" / "sources" / "gist-note.md").read_text(encoding="utf-8")
        self.assertIn('title: "Gist Note"', text)
        self.assertIn("# Gist Note", text)
        self.assertNotIn("<source title>", text)
        self.assertNotIn("<Source title>", text)

    def test_creates_concept_and_synthesis_pages(self):
        for family, page_type in (("concepts", "concept"), ("synthesis", "synthesis")):
            result = _run(
                [family, f"my-{page_type}", "--title", f"My {page_type.title()}", "--today", "2026-09-10"],
                self.root,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            target = self.root / "wiki" / family / f"my-{page_type}.md"
            text = target.read_text(encoding="utf-8")
            self.assertIn(f"title: \"My {page_type.title()}\"", text)
            self.assertIn(f"page_type: {page_type}", text)

    def test_nested_slug_creates_subdirectory(self):
        result = _run(
            ["entities", "people/ada-lovelace", "--title", "Ada Lovelace", "--today", "2026-09-10"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.root / "wiki" / "entities" / "people" / "ada-lovelace.md"
        self.assertTrue(target.exists())

    def test_tags_reliability_sensitivity_and_sources_applied(self):
        result = _run(
            [
                "entities",
                "tagged-entity",
                "--title",
                "Tagged Entity",
                "--tags",
                "alpha,beta",
                "--reliability",
                "high",
                "--sensitivity",
                "shareable",
                "--source",
                "raw/one.md",
                "--source",
                "sources/two.md",
                "--today",
                "2026-09-10",
            ],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.root / "wiki" / "entities" / "tagged-entity.md").read_text(encoding="utf-8")
        self.assertIn("tags: [alpha, beta]", text)
        self.assertIn("reliability: high", text)
        self.assertIn("sensitivity: shareable", text)
        self.assertIn('sources: ["raw/one.md", "sources/two.md"]', text)

    def test_refuses_to_overwrite_without_force(self):
        _run(["entities", "dup", "--title", "Dup", "--today", "2026-09-10"], self.root)
        result = _run(["entities", "dup", "--title", "Dup Again", "--today", "2026-09-10"], self.root)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.strip())

    def test_force_overwrites_existing_page(self):
        _run(["entities", "dup2", "--title", "Dup2", "--today", "2026-09-10"], self.root)
        result = _run(
            ["entities", "dup2", "--title", "Dup2 New Title", "--today", "2026-09-10", "--force"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.root / "wiki" / "entities" / "dup2.md").read_text(encoding="utf-8")
        self.assertIn('title: "Dup2 New Title"', text)

    def test_dry_run_does_not_write_file(self):
        result = _run(
            ["entities", "preview-only", "--title", "Preview Only", "--today", "2026-09-10", "--dry-run"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "wiki" / "entities" / "preview-only.md").exists())
        self.assertIn("Preview Only", result.stdout)

    def test_unknown_family_is_rejected(self):
        result = _run(["bogus", "x", "--title", "X", "--today", "2026-09-10"], self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("bogus", result.stderr)

    def test_invalid_slug_is_rejected(self):
        # Note: a slug beginning with "-" (e.g. "-leading-dash") is rejected
        # by argparse itself (exit 2, mistaken for an option) before reaching
        # new_page's own validation; that is an inherent CLI limitation, not
        # exercised here.
        for bad_slug in ("Bad_Slug", "UPPER", "trailing-slash/", "double//slash", "has_underscore"):
            result = _run(["entities", bad_slug, "--title", "X", "--today", "2026-09-10"], self.root)
            self.assertEqual(result.returncode, 1, bad_slug)

    def test_missing_title_is_rejected(self):
        result = _run(["entities", "no-title", "--today", "2026-09-10"], self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("title", result.stderr)

    def test_invalid_reliability_and_sensitivity_rejected(self):
        result = _run(
            ["entities", "bad-rel", "--title", "X", "--reliability", "extreme", "--today", "2026-09-10"],
            self.root,
        )
        self.assertEqual(result.returncode, 1)

        result = _run(
            ["entities", "bad-sens", "--title", "X", "--sensitivity", "top-secret", "--today", "2026-09-10"],
            self.root,
        )
        self.assertEqual(result.returncode, 1)

    def test_custom_wiki_root_and_config(self):
        alt_root = self.root / "alt-wiki"
        shutil.copytree(self.root / "wiki", alt_root)
        config_path = self.root / "alt.config.json"
        config_path.write_text(
            json.dumps(
                {
                    "wiki_root": "alt-wiki",
                    "page_families": {
                        "sources": "source",
                        "entities": "entity",
                        "concepts": "concept",
                        "synthesis": "synthesis",
                    },
                }
            ),
            encoding="utf-8",
        )
        result = _run(
            [
                "entities",
                "alt-entity",
                "--title",
                "Alt Entity",
                "--wiki-root",
                "alt-wiki",
                "--config",
                str(config_path),
                "--today",
                "2026-09-10",
            ],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((alt_root / "entities" / "alt-entity.md").exists())


if __name__ == "__main__":
    unittest.main()
