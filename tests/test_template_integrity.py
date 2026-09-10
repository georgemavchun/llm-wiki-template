"""Integrity tests for the shipped template.

The template must be a clean, working starting point: valid configuration,
templates that carry the schema's frontmatter, a wiki that lints without
errors, a tutorial source that passes the privacy preflight, placeholders
for the bootstrap to fill, and documentation whose relative links resolve.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import wiki_lint  # noqa: E402

REQUIRED_FRONTMATTER = ("title", "page_type", "reliability", "sensitivity", "sources", "created", "updated", "tags")
PLACEHOLDER_FILES = ("wiki/CLAUDE.md", "wiki/LOG.md", "README.md", "CUSTOMIZATIONS.md")
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"(?ms)^\s{0,3}(`{3,}|~{3,}).*?^\s{0,3}\1[ \t]*$")
INLINE_CODE = re.compile(r"(`+)(.*?)\1")


def prose_only(text: str) -> str:
    return INLINE_CODE.sub(" ", FENCE.sub(" ", text))


def load_config() -> dict:
    return json.loads((REPO / "wiki.config.json").read_text(encoding="utf-8"))


class ConfigTest(unittest.TestCase):
    def test_config_parses_and_has_required_keys(self):
        config = load_config()
        for key in ("schema_version", "wiki_root", "page_families", "caps", "index", "privacy", "share"):
            self.assertIn(key, config)
        self.assertEqual(config["wiki_root"], "wiki")
        self.assertEqual(config["share"]["destinations"], {})
        self.assertLess(config["caps"]["soft_lines"], config["caps"]["hard_lines"])

    def test_every_family_has_directory_and_template(self):
        config = load_config()
        wiki = REPO / config["wiki_root"]
        for directory, page_type in config["page_families"].items():
            with self.subTest(family=directory):
                self.assertTrue((wiki / directory).is_dir())
                template = wiki / "_templates" / f"{page_type}.md"
                self.assertTrue(template.is_file(), f"missing template {template.name}")
                text = template.read_text(encoding="utf-8")
                for key in REQUIRED_FRONTMATTER:
                    self.assertRegex(text, rf"(?m)^{key}:", f"{template.name} lacks {key}")
                self.assertIn(f"page_type: {page_type}", text)


class ShippedWikiTest(unittest.TestCase):
    def test_shipped_wiki_lints_clean(self):
        config = wiki_lint.load_config(None, REPO / "wiki")
        report = wiki_lint.build_report(REPO / "wiki", config, dt.date.today())
        errors = {k: v for k, v in report["errors"].items() if v}
        self.assertEqual(errors, {}, f"lint errors in shipped wiki: {json.dumps(errors, indent=1)}")
        self.assertEqual(report["counts"]["total"], 0)
        self.assertEqual(len(report["info"]["inbox_files"]), 1)

    def test_tutorial_source_passes_preflight(self):
        source = REPO / "wiki" / "raw" / "inbox" / "2026-09-10-welcome-to-your-llm-wiki.md"
        self.assertTrue(source.is_file())
        result = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "privacy_preflight.py"), str(source), "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_placeholders_present_for_bootstrap(self):
        for relative in PLACEHOLDER_FILES:
            with self.subTest(file=relative):
                text = (REPO / relative).read_text(encoding="utf-8")
                self.assertTrue("{{OWNER_NAME}}" in text or "{{START_DATE}}" in text, f"{relative} has no placeholder")

    def test_staging_is_ignored_and_untracked(self):
        gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".staging/", gitignore)
        self.assertIn(".claude/settings.local.json", gitignore)
        tracked = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", ".staging"], capture_output=True, text=True, check=False
        ).stdout.strip()
        self.assertEqual(tracked, "")

    def test_index_and_log_have_expected_shape(self):
        index = (REPO / "wiki" / "INDEX.md").read_text(encoding="utf-8")
        for heading in ("## Sources", "## Entities", "## Concepts", "## Synthesis"):
            self.assertIn(heading, index)
        log = (REPO / "wiki" / "LOG.md").read_text(encoding="utf-8")
        self.assertRegex(log, r"(?m)^## \[[^\]]+\] bootstrap \|")


class DocumentationLinksTest(unittest.TestCase):
    def doc_files(self):
        files = [REPO / "README.md", REPO / "SECURITY.md", REPO / "CONTRIBUTING.md", REPO / "wiki" / "README.md"]
        files.extend(sorted((REPO / "docs").glob("*.md")))
        return [f for f in files if f.is_file()]

    def test_relative_links_resolve(self):
        for doc in self.doc_files():
            text = prose_only(doc.read_text(encoding="utf-8"))
            for target in MD_LINK.findall(text):
                if target.startswith(("http://", "https://", "mailto:", "#")) or "<" in target:
                    continue
                clean = target.split("#", 1)[0]
                with self.subTest(doc=str(doc.relative_to(REPO)), target=target):
                    self.assertTrue((doc.parent / clean).resolve().exists(), f"{doc.relative_to(REPO)} links to missing {target}")

    def test_core_docs_exist(self):
        for relative in ("README.md", "docs/onboarding.md", "docs/privacy.md", "docs/skills.md", "docs/customizing.md", "docs/design.md", "docs/faq.md"):
            with self.subTest(doc=relative):
                self.assertTrue((REPO / relative).is_file(), f"missing {relative}")


if __name__ == "__main__":
    unittest.main()
