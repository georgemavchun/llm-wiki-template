from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import wiki_lint  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "wiki_lint.py"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _page_text(
    title: str = "Sample",
    page_type: str = "entity",
    reliability: str = "medium",
    sensitivity: str = "personal",
    sources: str = '["raw/note.txt"]',
    created: str = "2026-01-01",
    updated: str = "2026-01-01",
    body: str = "\n# Sample\n\nBody text.\n",
    omit_fields=(),
) -> str:
    fields = [
        ("title", f'"{title}"'),
        ("page_type", page_type),
        ("reliability", reliability),
        ("sensitivity", sensitivity),
        ("sources", sources),
        ("created", created),
        ("updated", updated),
    ]
    lines = ["---"]
    for name, value in fields:
        if name in omit_fields:
            continue
        lines.append(f"{name}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


class WikiFixture:
    """A minimal, valid, temporary wiki that each test mutates."""

    def __init__(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.wiki_root = self.root / "wiki"
        for name in ("sources", "entities", "concepts", "synthesis"):
            (self.wiki_root / name).mkdir(parents=True)
        (self.wiki_root / "_templates").mkdir()
        (self.wiki_root / "raw" / "inbox").mkdir(parents=True)
        (self.wiki_root / "raw" / "note.txt").write_text("raw note\n", encoding="utf-8")
        _write(self.root / "wiki.config.json", json.dumps(wiki_lint.DEFAULT_CONFIG))
        _write(
            self.wiki_root / "LOG.md",
            "# Wiki Log\n\n## [2026-01-01] bootstrap | wiki created\n",
        )
        _write(
            self.wiki_root / "INDEX.md",
            "# Wiki Index\n\n## Entities\n\n## Sources\n\n## Concepts\n\n## Synthesis\n",
        )

    def close(self) -> None:
        self.tempdir.cleanup()

    def add_page(self, relative_path: str, **kwargs) -> Path:
        path = self.wiki_root / relative_path
        _write(path, _page_text(**kwargs))
        return path

    def append_index_bullet(self, slug: str, index_name: str = "INDEX.md") -> None:
        path = self.wiki_root / index_name
        existing = path.read_text(encoding="utf-8") if path.is_file() else "# Index\n"
        path.write_text(existing.rstrip("\n") + f"\n- [[{slug}]]\n", encoding="utf-8")

    def write_index(self, index_name: str, content: str) -> None:
        _write(self.wiki_root / index_name, content)

    def config(self) -> dict:
        return wiki_lint.load_config(None, self.wiki_root)

    def report(self, today: date = date(2026, 1, 1)) -> dict:
        return wiki_lint.build_report(self.wiki_root, self.config(), today)

    def run_cli(self, *extra_args: str) -> subprocess.CompletedProcess:
        command = [sys.executable, str(SCRIPT), "--wiki-root", str(self.wiki_root)]
        command.extend(extra_args)
        return subprocess.run(command, capture_output=True, text=True, check=False)


class WikiLintTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = WikiFixture()

    def tearDown(self) -> None:
        self.fixture.close()


class CleanWikiTest(WikiLintTestCase):
    def test_clean_wiki_has_no_errors_and_exits_zero(self):
        self.fixture.add_page(
            "entities/person.md",
            page_type="entity",
            body="\n# Person\n\nSee [[idea]].\n",
        )
        self.fixture.add_page(
            "concepts/idea.md",
            page_type="concept",
            body="\n# Idea\n\nRelated to [[person]].\n",
        )
        self.fixture.add_page(
            "sources/note.md",
            page_type="source",
            body="\n# Note\n\nSee [[raw/note.txt]] and [[person]].\n",
        )
        self.fixture.add_page(
            "synthesis/summary.md",
            page_type="synthesis",
            body="\n# Summary\n\nBased on [[note]].\n",
        )
        for slug in ("person", "idea", "note", "summary"):
            self.fixture.append_index_bullet(slug)

        report = self.fixture.report()

        self.assertTrue(all(not findings for findings in report["errors"].values()))
        self.assertEqual(report["counts"]["total"], 4)

        result = self.fixture.run_cli("--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)


class MissingFrontmatterTest(WikiLintTestCase):
    def test_missing_fields_are_reported(self):
        self.fixture.add_page(
            "entities/incomplete.md", omit_fields=("sensitivity", "updated")
        )

        errors = self.fixture.report()["errors"]

        self.assertIn(
            {"path": "entities/incomplete.md", "missing": ["sensitivity", "updated"]},
            errors["missing_frontmatter"],
        )


class InvalidEnumTest(WikiLintTestCase):
    def test_bad_page_type_reliability_and_sensitivity_are_reported(self):
        self.fixture.add_page(
            "entities/bad.md",
            page_type="note",
            reliability="bogus",
            sensitivity="bogus",
        )

        errors = self.fixture.report()["errors"]
        by_field = {finding["field"]: finding["value"] for finding in errors["invalid_enum"]}

        self.assertEqual(
            by_field,
            {"page_type": "note", "reliability": "bogus", "sensitivity": "bogus"},
        )
        for finding in errors["invalid_enum"]:
            self.assertEqual(finding["path"], "entities/bad.md")


class InvalidDateTest(WikiLintTestCase):
    def test_malformed_and_impossible_dates_are_reported(self):
        self.fixture.add_page(
            "entities/dates.md", created="2026-13-40", updated="not-a-date"
        )

        errors = self.fixture.report()["errors"]
        by_field = {finding["field"]: finding["value"] for finding in errors["invalid_date"]}

        self.assertEqual(by_field, {"created": "2026-13-40", "updated": "not-a-date"})


class PageTypeMismatchTest(WikiLintTestCase):
    def test_declared_page_type_disagreeing_with_directory_is_reported(self):
        self.fixture.add_page("entities/wrong.md", page_type="concept")

        errors = self.fixture.report()["errors"]

        self.assertEqual(
            errors["page_type_mismatches"],
            [{"path": "entities/wrong.md", "expected": "entity", "actual": "concept"}],
        )
        # "concept" is a real family value, so this must not double as invalid_enum.
        self.assertEqual(errors["invalid_enum"], [])


class HardCapExceededTest(WikiLintTestCase):
    def test_page_over_hard_cap_is_reported(self):
        path = self.fixture.add_page("entities/long.md")
        filler = "\n".join(f"line {n}" for n in range(900))
        path.write_text(path.read_text(encoding="utf-8") + filler + "\n", encoding="utf-8")

        errors = self.fixture.report()["errors"]
        findings = errors["hard_cap_exceeded"]

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["path"], "entities/long.md")
        self.assertEqual(findings[0]["cap"], 800)
        self.assertGreater(findings[0]["lines"], 800)


class BrokenWikilinksTest(WikiLintTestCase):
    def test_link_to_missing_target_is_reported(self):
        self.fixture.add_page(
            "entities/person.md", body="\n# Person\n\nSee [[does-not-exist]].\n"
        )

        errors = self.fixture.report()["errors"]

        self.assertEqual(
            [(f["path"], f["target"]) for f in errors["broken_wikilinks"]],
            [("entities/person.md", "does-not-exist")],
        )

    def test_wikilinks_in_fences_and_inline_code_are_ignored(self):
        text = "\n".join(
            (
                "See `[[inline-missing]]` here.",
                "```markdown",
                "[[fenced-missing]]",
                "```",
                "Real link: [[also-missing]].",
            )
        )
        links = wiki_lint.extract_wikilinks(text)

        self.assertEqual([link.target for link in links], ["also-missing"])

    def test_raw_file_and_readme_targets_resolve(self):
        (self.fixture.wiki_root / "raw" / "file.txt").write_text("x\n", encoding="utf-8")
        (self.fixture.wiki_root / "sources" / "README.md").write_text(
            "# support\n", encoding="utf-8"
        )
        self.fixture.add_page(
            "entities/person.md",
            page_type="entity",
            body="\n# Person\n\nSee [[raw/file.txt]] and [[sources/README]].\n",
        )
        self.fixture.append_index_bullet("person")

        errors = self.fixture.report()["errors"]

        self.assertEqual(errors["broken_wikilinks"], [])


class DuplicateSlugsTest(WikiLintTestCase):
    def test_same_stem_in_different_families_is_reported(self):
        self.fixture.add_page("entities/shared.md", page_type="entity")
        self.fixture.add_page("concepts/shared.md", page_type="concept")

        errors = self.fixture.report()["errors"]

        self.assertEqual(
            errors["duplicate_slugs"],
            [
                {
                    "slug": "shared",
                    "paths": ["concepts/shared.md", "entities/shared.md"],
                }
            ],
        )


class BrokenSourceReferencesTest(WikiLintTestCase):
    def test_missing_raw_reference_is_reported(self):
        self.fixture.add_page(
            "sources/note.md",
            page_type="source",
            sources='["raw/note.txt", "raw/missing.txt"]',
        )

        errors = self.fixture.report()["errors"]

        self.assertEqual(
            errors["broken_source_references"],
            [{"path": "sources/note.md", "reference": "raw/missing.txt"}],
        )


class MissingIndexEntriesTest(WikiLintTestCase):
    def test_page_absent_from_both_root_and_shard_index_is_reported(self):
        self.fixture.add_page("entities/lonely.md", page_type="entity")

        errors = self.fixture.report()["errors"]
        findings = errors["missing_index_entries"]

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["path"], "entities/lonely.md")
        self.assertEqual(findings[0]["slug"], "lonely")
        self.assertIn("INDEX.md", findings[0]["indexes"])
        self.assertIn("INDEX-entities.md", findings[0]["indexes"])

    def test_sharded_index_entry_alone_satisfies_membership(self):
        self.fixture.add_page("entities/sharded.md", page_type="entity")
        # Root index only links to the shard, never lists the page directly.
        self.fixture.write_index(
            "INDEX.md", "# Wiki Index\n\n- [[INDEX-entities]]\n"
        )
        self.fixture.write_index(
            "INDEX-entities.md", "# Entities\n\n- [[sharded]]\n"
        )

        errors = self.fixture.report()["errors"]

        self.assertEqual(errors["missing_index_entries"], [])


class DuplicateIndexEntriesTest(WikiLintTestCase):
    def test_same_file_duplicate_bullet_is_reported(self):
        self.fixture.add_page("entities/twice.md", page_type="entity")
        self.fixture.append_index_bullet("twice")
        self.fixture.append_index_bullet("twice")

        errors = self.fixture.report()["errors"]
        findings = errors["duplicate_index_entries"]

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["slug"], "twice")
        self.assertEqual(len(findings[0]["occurrences"]), 2)

    def test_cross_file_duplicate_bullet_is_reported(self):
        self.fixture.add_page("entities/both.md", page_type="entity")
        self.fixture.write_index("INDEX.md", "# Wiki Index\n\n- [[both]]\n")
        self.fixture.write_index("INDEX-entities.md", "# Entities\n\n- [[both]]\n")

        errors = self.fixture.report()["errors"]
        findings = errors["duplicate_index_entries"]

        self.assertEqual(len(findings), 1)
        indexes = {occ["index"] for occ in findings[0]["occurrences"]}
        self.assertEqual(indexes, {"INDEX.md", "INDEX-entities.md"})


class FrontmatterLeakedIntoBodyTest(WikiLintTestCase):
    def test_leaked_sources_item_after_closing_delimiter_is_reported(self):
        path = self.fixture.add_page("entities/leaked.md")
        path.write_text(
            path.read_text(encoding="utf-8").rstrip("\n") + '\n  - "sources/other.md"\n',
            encoding="utf-8",
        )

        errors = self.fixture.report()["errors"]
        findings = errors["frontmatter_leaked_into_body"]

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["path"], "entities/leaked.md")
        self.assertEqual(findings[0]["items"][0]["text"], '- "sources/other.md"')

    def test_fenced_yaml_example_is_not_flagged(self):
        path = self.fixture.add_page("entities/example.md")
        path.write_text(
            path.read_text(encoding="utf-8").rstrip("\n")
            + '\n\n```yaml\nsources:\n  - "sources/other.md"\n```\n',
            encoding="utf-8",
        )

        errors = self.fixture.report()["errors"]

        self.assertEqual(errors["frontmatter_leaked_into_body"], [])


class ConfigInvalidTest(WikiLintTestCase):
    def test_malformed_json_raises_config_error(self):
        (self.fixture.root / "wiki.config.json").write_text("{not json", encoding="utf-8")

        with self.assertRaises(wiki_lint.ConfigError):
            wiki_lint.load_config(None, self.fixture.wiki_root)

    def test_wrong_type_raises_config_error(self):
        (self.fixture.root / "wiki.config.json").write_text(
            json.dumps({"caps": {"soft_lines": "not-a-number"}}), encoding="utf-8"
        )

        with self.assertRaises(wiki_lint.ConfigError):
            wiki_lint.load_config(None, self.fixture.wiki_root)

    def test_cli_exits_one_and_reports_config_invalid(self):
        (self.fixture.root / "wiki.config.json").write_text("{not json", encoding="utf-8")

        result = self.fixture.run_cli("--format", "json")

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["errors"]["config_invalid"]), 1)

    def test_absent_config_file_falls_back_to_defaults(self):
        (self.fixture.root / "wiki.config.json").unlink()

        config = wiki_lint.load_config(None, self.fixture.wiki_root)

        self.assertEqual(config, wiki_lint.DEFAULT_CONFIG)


class OrphansWarningTest(WikiLintTestCase):
    def test_page_with_no_inbound_link_is_an_orphan(self):
        self.fixture.add_page("entities/isolated.md", page_type="entity")
        self.fixture.add_page(
            "entities/other.md", page_type="entity", body="\n# Other\n\nNo links here.\n"
        )
        self.fixture.append_index_bullet("isolated")
        self.fixture.append_index_bullet("other")

        warnings = self.fixture.report()["warnings"]

        orphan_paths = {f["path"] for f in warnings["orphans"]}
        self.assertIn("entities/isolated.md", orphan_paths)
        self.assertIn("entities/other.md", orphan_paths)

    def test_linked_page_is_not_an_orphan(self):
        self.fixture.add_page(
            "entities/a.md", page_type="entity", body="\n# A\n\nSee [[b]].\n"
        )
        self.fixture.add_page("entities/b.md", page_type="entity")
        self.fixture.append_index_bullet("a")
        self.fixture.append_index_bullet("b")

        warnings = self.fixture.report()["warnings"]

        orphan_paths = {f["path"] for f in warnings["orphans"]}
        self.assertNotIn("entities/b.md", orphan_paths)
        # "a" links out but nothing links to it, so it is still an orphan.
        self.assertIn("entities/a.md", orphan_paths)


class SoftCapExceededTest(WikiLintTestCase):
    def test_page_between_soft_and_hard_cap_warns_only(self):
        path = self.fixture.add_page("entities/mid.md")
        filler = "\n".join(f"line {n}" for n in range(450))
        path.write_text(path.read_text(encoding="utf-8") + filler + "\n", encoding="utf-8")

        report = self.fixture.report()

        self.assertEqual(report["errors"]["hard_cap_exceeded"], [])
        findings = report["warnings"]["soft_cap_exceeded"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["path"], "entities/mid.md")
        self.assertEqual(findings[0]["cap"], 400)


class StaleLowReliabilityTest(WikiLintTestCase):
    def test_old_low_reliability_page_warns(self):
        self.fixture.add_page(
            "entities/old.md", reliability="low", updated="2026-01-01"
        )

        recent = self.fixture.report(today=date(2026, 1, 10))
        stale = self.fixture.report(today=date(2026, 3, 1))

        self.assertEqual(recent["warnings"]["stale_low_reliability"], [])
        findings = stale["warnings"]["stale_low_reliability"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["path"], "entities/old.md")
        self.assertGreater(findings[0]["days"], 30)

    def test_medium_reliability_never_triggers_this_warning(self):
        self.fixture.add_page(
            "entities/old.md", reliability="medium", updated="2026-01-01"
        )

        report = self.fixture.report(today=date(2026, 6, 1))

        self.assertEqual(report["warnings"]["stale_low_reliability"], [])


class StalePendingReviewTest(WikiLintTestCase):
    def test_real_content_in_old_pending_review_warns(self):
        self.fixture.add_page(
            "entities/flagged.md",
            updated="2026-01-01",
            body="\n# Flagged\n\n## Pending Review\n\nUnverified claim about X.\n",
        )

        report = self.fixture.report(today=date(2026, 3, 1))

        findings = report["warnings"]["stale_pending_review"]
        self.assertEqual([f["path"] for f in findings], ["entities/flagged.md"])

    def test_placeholder_only_pending_review_does_not_warn(self):
        self.fixture.add_page(
            "entities/clean.md",
            updated="2026-01-01",
            body=(
                "\n# Clean\n\n## Pending Review\n\n"
                "<Unverified or contradicted claims. Delete the section if empty.>\n"
            ),
        )

        report = self.fixture.report(today=date(2026, 3, 1))

        self.assertEqual(report["warnings"]["stale_pending_review"], [])

    def test_recent_pending_review_does_not_warn(self):
        self.fixture.add_page(
            "entities/fresh.md",
            updated="2026-01-01",
            body="\n# Fresh\n\n## Pending Review\n\nUnverified claim about X.\n",
        )

        report = self.fixture.report(today=date(2026, 1, 10))

        self.assertEqual(report["warnings"]["stale_pending_review"], [])


class ColdPagesTest(WikiLintTestCase):
    def test_page_untouched_past_threshold_warns(self):
        self.fixture.add_page("entities/frozen.md", updated="2026-01-01")

        fresh = self.fixture.report(today=date(2026, 3, 1))
        cold = self.fixture.report(today=date(2026, 8, 1))

        self.assertEqual(fresh["warnings"]["cold_pages"], [])
        findings = cold["warnings"]["cold_pages"]
        self.assertEqual([f["path"] for f in findings], ["entities/frozen.md"])
        self.assertGreater(findings[0]["days"], 180)


class TemplatePlaceholdersTest(WikiLintTestCase):
    def test_leftover_slot_placeholder_warns(self):
        self.fixture.add_page(
            "entities/unfinished.md",
            body="\n# Unfinished\n\nCreated on <YYYY-MM-DD> for <slug>.\n",
        )

        warnings = self.fixture.report()["warnings"]
        findings = warnings["template_placeholders"]

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["path"], "entities/unfinished.md")
        self.assertIn("<YYYY-MM-DD>", findings[0]["matches"])
        self.assertIn("<slug>", findings[0]["matches"])

    def test_brace_placeholder_warns(self):
        self.fixture.add_page(
            "entities/owner.md", body="\n# Owner\n\nOwner: {{OWNER_NAME}}\n"
        )

        findings = self.fixture.report()["warnings"]["template_placeholders"]

        self.assertEqual(len(findings), 1)
        self.assertIn("{{OWNER_NAME}}", findings[0]["matches"])

    def test_placeholder_inside_code_is_ignored(self):
        self.fixture.add_page(
            "entities/documented.md",
            body="\n# Documented\n\nExample: `<slug>` and:\n\n```\n<slug>\n```\n",
        )

        findings = self.fixture.report()["warnings"]["template_placeholders"]

        self.assertEqual(findings, [])


class NestedPagesTest(WikiLintTestCase):
    def test_nested_page_is_discovered_under_its_family(self):
        self.fixture.add_page(
            "entities/people/x.md", page_type="entity"
        )
        self.fixture.append_index_bullet("x")

        report = self.fixture.report()
        pages = {p["path"]: p for p in report["pages"]}

        self.assertIn("entities/people/x.md", pages)
        self.assertEqual(pages["entities/people/x.md"]["page_type"], "entity")
        self.assertEqual(pages["entities/people/x.md"]["slug"], "x")
        self.assertEqual(report["counts"]["entities"], 1)

        directories = {
            d["path"]: d["pages"] for d in report["info"]["scale"]["directories"]
        }
        self.assertEqual(directories.get("entities/people"), 1)


class BriefOutputTest(WikiLintTestCase):
    def test_brief_output_is_short_and_informative(self):
        self.fixture.add_page("entities/person.md", page_type="entity")
        self.fixture.append_index_bullet("person")

        report = self.fixture.report()
        text = wiki_lint.format_brief(report)
        lines = text.rstrip("\n").splitlines()

        self.assertLessEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("Wiki:"))
        self.assertIn("errors", lines[0])
        self.assertIn("warnings", lines[0])
        self.assertIn("raw/inbox", lines[0])
        self.assertTrue(any(line.startswith("Last log:") for line in lines))

    def test_brief_cli_output_matches_exit_code_rules(self):
        self.fixture.add_page("entities/person.md", page_type="entity")
        self.fixture.append_index_bullet("person")

        result = self.fixture.run_cli("--brief")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(len(result.stdout.rstrip("\n").splitlines()), 4)

    def test_brief_lists_nonzero_findings_by_type(self):
        self.fixture.add_page("entities/lonely.md", page_type="entity")

        report = self.fixture.report()
        text = wiki_lint.format_brief(report)

        self.assertIn("Errors: missing_index_entries", text)


class TextOutputTest(WikiLintTestCase):
    def test_text_report_contains_required_headings(self):
        self.fixture.add_page("entities/person.md", page_type="entity")
        self.fixture.append_index_bullet("person")

        report = self.fixture.report()
        text = wiki_lint.format_text(report, date(2026, 1, 1))

        self.assertIn("# Wiki lint — 2026-01-01", text)
        self.assertIn("## Summary", text)
        self.assertIn("## Errors", text)
        self.assertIn("## Warnings", text)
        self.assertIn("## Info", text)
        self.assertIn("No errors.", text)

    def test_text_report_lists_error_subsections(self):
        self.fixture.add_page("entities/lonely.md", page_type="entity")

        report = self.fixture.report()
        text = wiki_lint.format_text(report, date(2026, 1, 1))

        self.assertIn("### missing_index_entries", text)


class JsonKeysStableTest(WikiLintTestCase):
    def test_top_level_and_nested_keys_are_stable_regardless_of_content(self):
        expected_top = {
            "caps",
            "counts",
            "pages",
            "index_documents",
            "errors",
            "warnings",
            "info",
            "config_path",
            "wiki_root",
        }
        empty_report = self.fixture.report()
        self.assertEqual(set(empty_report), expected_top)
        self.assertEqual(set(empty_report["errors"]), set(wiki_lint.ERROR_KEYS))
        self.assertEqual(set(empty_report["warnings"]), set(wiki_lint.WARNING_KEYS))

        self.fixture.add_page("entities/lonely.md", page_type="entity")
        populated_report = self.fixture.report()
        self.assertEqual(set(populated_report), expected_top)
        self.assertEqual(set(populated_report["errors"]), set(wiki_lint.ERROR_KEYS))
        self.assertEqual(set(populated_report["warnings"]), set(wiki_lint.WARNING_KEYS))

    def test_cli_json_output_round_trips(self):
        self.fixture.add_page("entities/person.md", page_type="entity")
        self.fixture.append_index_bullet("person")

        result = self.fixture.run_cli("--format", "json")
        payload = json.loads(result.stdout)

        self.assertEqual(set(payload), {
            "caps", "counts", "pages", "index_documents",
            "errors", "warnings", "info", "config_path", "wiki_root",
        })


class ExitCodeTest(WikiLintTestCase):
    def test_clean_wiki_exits_zero(self):
        self.fixture.add_page("entities/person.md", page_type="entity")
        self.fixture.append_index_bullet("person")

        result = self.fixture.run_cli("--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wiki_with_error_exits_two(self):
        self.fixture.add_page("entities/lonely.md", page_type="entity")

        result = self.fixture.run_cli("--format", "json")

        self.assertEqual(result.returncode, 2)

    def test_missing_wiki_root_exits_one(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--wiki-root",
                str(self.fixture.root / "does-not-exist"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stderr)

    def test_invalid_format_choice_exits_one(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--wiki-root",
                str(self.fixture.wiki_root),
                "--format",
                "yaml",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)

    def test_invalid_today_exits_one(self):
        result = self.fixture.run_cli("--today", "not-a-date")

        self.assertEqual(result.returncode, 1)

    def test_main_function_returns_ints_directly(self):
        self.fixture.add_page("entities/person.md", page_type="entity")
        self.fixture.append_index_bullet("person")

        code = wiki_lint.main(
            ["--wiki-root", str(self.fixture.wiki_root), "--format", "json"]
        )

        self.assertEqual(code, 0)


class ShippedTemplateWikiTest(unittest.TestCase):
    def test_shipped_wiki_lints_clean(self):
        wiki_root = REPO_ROOT / "wiki"
        config = wiki_lint.load_config(None, wiki_root)

        report = wiki_lint.build_report(wiki_root, config, date(2026, 9, 10))

        self.assertTrue(
            all(not findings for findings in report["errors"].values()),
            report["errors"],
        )
        self.assertEqual(report["counts"]["total"], 0)
        self.assertEqual(len(report["info"]["inbox_files"]), 1)

    def test_shipped_wiki_cli_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--wiki-root", str(REPO_ROOT / "wiki"), "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(REPO_ROOT),
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
