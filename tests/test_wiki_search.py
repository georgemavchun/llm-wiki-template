from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "wiki_search.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import wiki_search  # noqa: E402

CONFIG = {
    "wiki_root": "wiki",
    "page_families": {
        "sources": "source",
        "entities": "entity",
        "concepts": "concept",
        "synthesis": "synthesis",
    },
}


def _page(title: str, page_type: str, tags, headings, body: str) -> str:
    tags_str = "[" + ", ".join(tags) + "]"
    heading_lines = "\n\n".join(f"## {h}\n\n{body}" for h in headings) if headings else body
    return (
        "---\n"
        f'title: "{title}"\n'
        f"page_type: {page_type}\n"
        "reliability: medium\n"
        "sensitivity: personal\n"
        'sources: ["sources/x.md"]\n'
        "created: 2026-01-01\n"
        "updated: 2026-01-01\n"
        f"tags: {tags_str}\n"
        "---\n\n"
        f"# {title}\n\n{heading_lines}\n"
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class WikiSearchIndexTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.wiki_root = Path(self.tempdir.name) / "wiki"
        for family in ("sources", "entities", "concepts", "synthesis"):
            (self.wiki_root / family).mkdir(parents=True, exist_ok=True)
        (self.wiki_root / "raw").mkdir(parents=True, exist_ok=True)
        (self.wiki_root / "_templates").mkdir(parents=True, exist_ok=True)

    def test_empty_wiki_has_no_docs_and_no_matches(self):
        index = wiki_search.build_index(self.wiki_root, CONFIG)
        self.assertEqual(index.n_docs, 0)
        self.assertEqual(wiki_search.search(index, "anything"), [])

    def test_finds_page_by_title_term(self):
        _write(
            self.wiki_root / "entities" / "karpathy.md",
            _page("Andrej Karpathy", "entity", ["ai"], [], "A researcher known for neural networks."),
        )
        index = wiki_search.build_index(self.wiki_root, CONFIG)
        self.assertEqual(index.n_docs, 1)
        results = wiki_search.search(index, "karpathy")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["slug"], "karpathy")
        self.assertIn("karpathy", results[0]["matched_terms"])

    def test_title_weighted_above_body_only_mention(self):
        _write(
            self.wiki_root / "entities" / "title-match.md",
            _page("Compounding Knowledge Base", "entity", [], [], "Nothing else notable."),
        )
        _write(
            self.wiki_root / "concepts" / "body-match.md",
            _page("Other Concept", "concept", [], [], "This page briefly mentions compounding effects."),
        )
        index = wiki_search.build_index(self.wiki_root, CONFIG)
        results = wiki_search.search(index, "compounding")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["slug"], "title-match")
        self.assertGreater(results[0]["score"], results[1]["score"])

    def test_excludes_support_and_raw_and_template_files(self):
        _write(self.wiki_root / "entities" / "README.md", "not a real page")
        _write(self.wiki_root / "entities" / "CLAUDE.md", "not a real page")
        _write(self.wiki_root / "raw" / "inbox" / "note.md", "raw content karpathy")
        _write(self.wiki_root / "_templates" / "entity.md", "template karpathy placeholder")
        _write(self.wiki_root / "INDEX.md", "index karpathy")
        _write(self.wiki_root / "LOG.md", "log karpathy")
        index = wiki_search.build_index(self.wiki_root, CONFIG)
        self.assertEqual(index.n_docs, 0)

    def test_cyrillic_query_matches_cyrillic_content(self):
        _write(
            self.wiki_root / "entities" / "orienteering.md",
            _page("Ориентирование", "entity", [], [], "Клуб Фарум Тисвильде проводит тренировки."),
        )
        index = wiki_search.build_index(self.wiki_root, CONFIG)
        results = wiki_search.search(index, "ориентирование")
        self.assertEqual(len(results), 1)

    def test_stemming_strips_trailing_s_for_long_tokens(self):
        self.assertEqual(wiki_search.tokenize("wikis"), ["wiki"])
        self.assertEqual(wiki_search.tokenize("cats"), ["cats"])  # len 4, not stemmed

    def test_short_tokens_dropped(self):
        self.assertNotIn("a", wiki_search.tokenize("a an the wiki"))


class WikiSearchCliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.wiki_root = self.root / "wiki"
        for family in ("sources", "entities", "concepts", "synthesis"):
            (self.wiki_root / family).mkdir(parents=True, exist_ok=True)
        (self.root / "wiki.config.json").write_text(json.dumps(CONFIG), encoding="utf-8")

    def _run(self, args):
        return subprocess.run(
            [sys.executable, str(SCRIPT)] + args,
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )

    def test_no_matches_on_empty_wiki(self):
        result = self._run(["nonexistent query terms"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "no matches")

    def test_text_output_format(self):
        _write(
            self.wiki_root / "entities" / "karpathy.md",
            _page("Andrej Karpathy", "entity", ["ai"], [], "LLM wiki pattern."),
        )
        result = self._run(["karpathy", "--format", "text"])
        self.assertEqual(result.returncode, 0)
        line = result.stdout.strip().splitlines()[0]
        self.assertIn("karpathy.md", line)
        self.assertIn("— Andrej Karpathy", line)

    def test_json_output_format(self):
        _write(
            self.wiki_root / "entities" / "karpathy.md",
            _page("Andrej Karpathy", "entity", ["ai"], [], "LLM wiki pattern."),
        )
        result = self._run(["karpathy", "--format", "json"])
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["slug"], "karpathy")
        self.assertIn("score", payload[0])
        self.assertIn("matched_terms", payload[0])

    def test_top_limits_results(self):
        for i in range(5):
            _write(
                self.wiki_root / "entities" / f"page-{i}.md",
                _page(f"Karpathy Page {i}", "entity", [], [], "karpathy karpathy karpathy"),
            )
        result = self._run(["karpathy", "--top", "2", "--format", "json"])
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload), 2)


if __name__ == "__main__":
    unittest.main()
