"""Contract tests for skills, agent definitions and settings.

These tests keep the agent-facing surface consistent: every skill has portable
frontmatter whose name matches its directory, every script or reference a
skill mentions exists, the shared settings parse and point at real hook
scripts, and no personal data from the template author's environment leaks
into the template.
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO / ".claude" / "skills"
EXPECTED_SKILLS = {
    "wiki-setup",
    "wiki-ingest",
    "wiki-ingest-light",
    "wiki-ingest-meetings",
    "wiki-crystallize",
    "wiki-query",
    "wiki-lint",
    "wiki-evolve",
    "wiki-share",
}
MAX_SKILL_BODY_LINES = 300
MAX_FRONTMATTER_CHARS = 1024

# Strings that must never appear in the template. They identify the author's
# employer, colleagues, side projects or machine. Keep this list boring and
# specific; it is a leak detector, not a style guide.
LEAK_DENYLIST = (
    "Moneff",
    "moneff",
    "Farkhod",
    "Sanjar",
    "Dolgolev",
    "Bakhtiyor",
    "Nigora",
    "Konstantinos",
    "Ovidiu",
    "Artemii",
    "Zubarevich",
    "ClearBank",
    "/Users/georgemavchun",
    "CursorProjects",
    "Staminity",
)
LEAK_EXEMPT = {"LICENSE"}

SCRIPT_REF = re.compile(r"scripts/(?:hooks/)?[a-z_]+\.py")
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)")
FENCE = re.compile(r"(?ms)^\s{0,3}(`{3,}|~{3,}).*?^\s{0,3}\1[ \t]*$")
INLINE_CODE = re.compile(r"(`+)(.*?)\1")


def prose_only(text: str) -> str:
    """Strip fenced blocks and inline code so example links are not checked."""
    return INLINE_CODE.sub(" ", FENCE.sub(" ", text))


def parse_frontmatter(text: str) -> dict:
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if match:
            value = match.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            fields[match.group(1)] = value
    return fields


def frontmatter_block(text: str) -> str:
    lines = text.lstrip("﻿").splitlines()
    block = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        block.append(line)
    return "\n".join(block)


def body_lines(text: str) -> int:
    lines = text.splitlines()
    closing = None
    for position in range(1, len(lines)):
        if lines[position].strip() == "---":
            closing = position
            break
    return len(lines) - (closing + 1 if closing is not None else 0)


def tracked_or_present_files() -> list:
    """Return repository text files, preferring git's view when available."""
    try:
        output = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "-co", "--exclude-standard", "-z"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        paths = [REPO / p for p in output.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        paths = [p for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [p for p in paths if p.is_file() and p.suffix in {".md", ".py", ".json", ".yml", ".yaml", ".sh", ".txt", ""} and ".git" not in p.parts]


class SkillContractTest(unittest.TestCase):
    def setUp(self):
        self.skills = {p.name: p for p in SKILLS_DIR.iterdir() if p.is_dir()}

    def test_expected_skills_present(self):
        self.assertEqual(set(self.skills), EXPECTED_SKILLS)

    def test_every_skill_has_valid_frontmatter(self):
        for name, path in sorted(self.skills.items()):
            with self.subTest(skill=name):
                skill_md = path / "SKILL.md"
                self.assertTrue(skill_md.is_file(), f"{name} lacks SKILL.md")
                text = skill_md.read_text(encoding="utf-8")
                fields = parse_frontmatter(text)
                self.assertEqual(fields.get("name"), name)
                self.assertTrue(fields.get("description"), f"{name} lacks a description")
                self.assertTrue(
                    fields["description"].startswith("Use when"),
                    f"{name} description should start with 'Use when'",
                )
                self.assertEqual(
                    set(fields), {"name", "description"},
                    f"{name} uses non-portable frontmatter fields: {sorted(set(fields) - {'name', 'description'})}",
                )
                self.assertLessEqual(len(frontmatter_block(text)), MAX_FRONTMATTER_CHARS)
                self.assertLessEqual(body_lines(text), MAX_SKILL_BODY_LINES, f"{name} body is too long")

    def test_skill_names_are_slugs(self):
        for name in self.skills:
            self.assertRegex(name, r"^[a-z0-9][a-z0-9-]*$")

    def test_referenced_scripts_exist(self):
        for name, path in sorted(self.skills.items()):
            for md in path.rglob("*.md"):
                text = md.read_text(encoding="utf-8")
                for ref in sorted(set(SCRIPT_REF.findall(text))):
                    with self.subTest(skill=name, ref=ref):
                        self.assertTrue((REPO / ref).is_file(), f"{md.relative_to(REPO)} references missing {ref}")

    def test_relative_markdown_links_resolve(self):
        for name, path in sorted(self.skills.items()):
            for md in path.rglob("*.md"):
                text = prose_only(md.read_text(encoding="utf-8"))
                for target in MD_LINK.findall(text):
                    if target.startswith(("http://", "https://", "mailto:")) or "<" in target:
                        continue
                    with self.subTest(file=str(md.relative_to(REPO)), target=target):
                        resolved = (md.parent / target).resolve()
                        self.assertTrue(resolved.exists(), f"{md.relative_to(REPO)} links to missing {target}")

    def test_explicit_repo_paths_exist(self):
        pattern = re.compile(r"`(\.claude/[A-Za-z0-9_./-]+|docs/[a-z0-9-]+\.md|wiki/[A-Za-z0-9_./-]+\.md)`")
        for name, path in sorted(self.skills.items()):
            text = (path / "SKILL.md").read_text(encoding="utf-8")
            for ref in sorted(set(pattern.findall(text))):
                if "<" in ref or "*" in ref:
                    continue
                with self.subTest(skill=name, ref=ref):
                    self.assertTrue((REPO / ref).exists(), f"{name} mentions missing path {ref}")

    def test_root_claude_md_lists_every_skill(self):
        text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
        for name in EXPECTED_SKILLS:
            self.assertIn(f"`{name}`", text)

    def test_schema_workflow_outline_matches_skills(self):
        schema = (REPO / "wiki" / "CLAUDE.md").read_text(encoding="utf-8")
        for heading in ("Ingest", "Ingest-light", "Ingest-meetings", "Crystallize", "Query", "Lint", "Evolve", "Share"):
            self.assertIn(f"**{heading}**", schema)


class AgentAndSettingsTest(unittest.TestCase):
    def test_wiki_scout_agent_definition(self):
        text = (REPO / ".claude" / "agents" / "wiki-scout.md").read_text(encoding="utf-8")
        fields = parse_frontmatter(text)
        self.assertEqual(fields.get("name"), "wiki-scout")
        self.assertTrue(fields.get("description"))
        self.assertEqual(fields.get("model"), "haiku")
        self.assertIn("Read", fields.get("tools", ""))

    def test_settings_json_hooks_point_at_existing_scripts(self):
        settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("Edit(./wiki/raw/**)", settings["permissions"]["deny"])
        hooks = settings["hooks"]
        for event in ("PreToolUse", "SessionStart"):
            self.assertIn(event, hooks)
            for group in hooks[event]:
                for hook in group["hooks"]:
                    match = SCRIPT_REF.search(hook["command"])
                    self.assertIsNotNone(match, hook["command"])
                    self.assertTrue((REPO / match.group(0)).is_file(), f"missing hook script {match.group(0)}")

    def test_raw_immutability_rule_scoped_to_raw(self):
        text = (REPO / ".claude" / "rules" / "raw-immutability.md").read_text(encoding="utf-8")
        self.assertIn('"wiki/raw/**"', text)


class LeakDetectorTest(unittest.TestCase):
    def test_no_author_specific_strings(self):
        offenders = []
        for path in tracked_or_present_files():
            if path.name in LEAK_EXEMPT:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for needle in LEAK_DENYLIST:
                if needle in text:
                    offenders.append(f"{path.relative_to(REPO)}: {needle}")
        self.assertEqual(offenders, [], "author-specific strings found:\n" + "\n".join(offenders))

    def test_no_absolute_home_paths(self):
        offenders = []
        for path in tracked_or_present_files():
            if path.name in LEAK_EXEMPT:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if re.search(r"/Users/[A-Za-z]|/home/[A-Za-z]", text):
                offenders.append(str(path.relative_to(REPO)))
        self.assertEqual(offenders, [], "absolute home paths found in: " + ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()
