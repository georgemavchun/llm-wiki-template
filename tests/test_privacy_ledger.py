from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCRIPT = SCRIPTS_DIR / "validate_privacy_ledger.py"

sys.path.insert(0, str(SCRIPTS_DIR))

import validate_privacy_ledger as vpl  # noqa: E402


SOURCE_TEXT = "00:01 Ada: We reviewed the onboarding workflow.\n"
TAXONOMY_VERSION = vpl.DEFAULT_TAXONOMY_VERSION
TEAM_CONFIG = {
    "privacy": {"taxonomy_version": TAXONOMY_VERSION},
    "share": {"destinations": {"team": {"path": "../team-wiki"}}},
}
_USE_TEAM_CONFIG = object()


def valid_entry(block_id="B001", source_locator="L1-L1"):
    """A shareable entry destined for the 'team' wiki (needs TEAM_CONFIG)."""
    return {
        "block_id": block_id,
        "source_locator": source_locator,
        "class": "shareable",
        "action": "keep",
        "confidence": "high",
        "review_state": "approved",
        "proposal_bucket": "safe",
        "reason_codes": ["public-approved"],
        "destinations": ["team"],
    }


def relaxed_entry(block_id="B001", source_locator="L1-L1", sensitivity_class="shareable", action="keep"):
    """An entry using the no-destinations-configured relaxation: excluded + approved.

    proposal_bucket and destinations are omitted to exercise the optional-field defaults.
    """
    return {
        "block_id": block_id,
        "source_locator": source_locator,
        "class": sensitivity_class,
        "action": action,
        "confidence": "high",
        "review_state": "approved",
        "reason_codes": ["public-approved"] if sensitivity_class == "shareable" else ["internal-architecture"],
    }


def valid_payload(entries=None, source_text=SOURCE_TEXT, taxonomy_version=None):
    version = taxonomy_version if taxonomy_version is not None else TAXONOMY_VERSION
    return {
        "taxonomy_version": version,
        "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "source_line_count": len(source_text.splitlines()),
        "entries": entries if entries is not None else [valid_entry()],
    }


class PrivacyLedgerUnitTest(unittest.TestCase):
    """Direct-import tests against the public functions."""

    def test_load_config_defaults_when_nothing_found(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger_path = str(Path(tmp_dir) / "ledger.json")
            config = vpl.load_config(None, ledger_path)
        self.assertEqual(config["taxonomy_version"], vpl.DEFAULT_TAXONOMY_VERSION)
        self.assertEqual(config["destinations"], set())

    def test_load_config_discovers_wiki_config_in_ledger_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "wiki.config.json").write_text(json.dumps(TEAM_CONFIG), encoding="utf-8")
            ledger_path = str(Path(tmp_dir) / "ledger.json")
            config = vpl.load_config(None, ledger_path)
        self.assertEqual(config["destinations"], {"team"})

    def test_load_config_explicit_path_overrides_discovery(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "wiki.config.json").write_text(
                json.dumps({"share": {"destinations": {"wrong": {}}}}), encoding="utf-8"
            )
            other_dir = Path(tmp_dir) / "elsewhere"
            other_dir.mkdir()
            explicit_config = other_dir / "custom.json"
            explicit_config.write_text(json.dumps(TEAM_CONFIG), encoding="utf-8")
            ledger_path = str(Path(tmp_dir) / "ledger.json")
            config = vpl.load_config(str(explicit_config), ledger_path)
        self.assertEqual(config["destinations"], {"team"})

    def test_load_config_explicit_missing_path_raises(self):
        with self.assertRaises(vpl.ConfigError):
            vpl.load_config("/definitely/does/not/exist/wiki.config.json", None)

    def test_validate_ledger_relaxation_accepts_excluded_shareable_without_destinations(self):
        payload = valid_payload([relaxed_entry()])
        config = {"taxonomy_version": TAXONOMY_VERSION, "destinations": set()}
        errors = vpl.validate_ledger(payload, SOURCE_TEXT, config)
        self.assertEqual(errors, [])

    def test_validate_ledger_relaxation_accepts_excluded_restricted_without_destinations(self):
        payload = valid_payload([relaxed_entry(sensitivity_class="restricted", action="generalize")])
        config = {"taxonomy_version": TAXONOMY_VERSION, "destinations": set()}
        errors = vpl.validate_ledger(payload, SOURCE_TEXT, config)
        self.assertEqual(errors, [])

    def test_validate_ledger_personal_still_requires_blocked_under_relaxation(self):
        entry = relaxed_entry(sensitivity_class="personal", action="omit")
        entry["reason_codes"] = ["personal-data"]
        payload = valid_payload([entry])
        config = {"taxonomy_version": TAXONOMY_VERSION, "destinations": set()}
        errors = vpl.validate_ledger(payload, SOURCE_TEXT, config)
        rules = {error.rule for error in errors}
        self.assertIn("personal-review", rules)


class PrivacyLedgerCliTest(unittest.TestCase):
    def run_ledger(self, payload, source_text=SOURCE_TEXT, config=_USE_TEAM_CONFIG, extra_args=None):
        self.assertTrue(SCRIPT.exists(), f"missing ledger validator: {SCRIPT}")
        if config is _USE_TEAM_CONFIG:
            config = TEAM_CONFIG
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger = Path(tmp_dir) / "ledger.json"
            source = Path(tmp_dir) / "transcript.txt"
            ledger.write_text(json.dumps(payload), encoding="utf-8")
            source.write_text(source_text, encoding="utf-8")
            if config is not None:
                (Path(tmp_dir) / "wiki.config.json").write_text(
                    json.dumps(config), encoding="utf-8"
                )
            args = [
                sys.executable,
                str(SCRIPT),
                str(ledger),
                "--source",
                str(source),
                "--format",
                "json",
            ]
            if extra_args:
                args.extend(extra_args)
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False,
                cwd=tmp_dir,
            )
        return result

    def assert_invalid(self, payload, rule, config=_USE_TEAM_CONFIG):
        result = self.run_ledger(payload, config=config)
        self.assertEqual(result.returncode, 2, result.stderr)
        body = json.loads(result.stdout)
        self.assertEqual(body["status"], "invalid")
        self.assertIn(rule, {error["rule"] for error in body["errors"]})
        for error in body["errors"]:
            self.assertEqual(set(error), {"block_id", "rule"})

    def test_valid_ledger_passes(self):
        result = self.run_ledger(valid_payload())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"status": "valid"})

    def test_valid_quarantine_ledger_returns_blocked_status(self):
        entry = valid_entry()
        entry.update(
            {
                "class": "quarantine",
                "action": "placeholder",
                "review_state": "blocked",
                "proposal_bucket": "excluded",
                "reason_codes": ["credentials"],
                "destinations": [],
            }
        )
        result = self.run_ledger(valid_payload([entry]))
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"blocked_blocks": ["B001"], "status": "blocked"},
        )

    def test_unknown_taxonomy_version_fails(self):
        self.assert_invalid(valid_payload(taxonomy_version="1900-01-01"), "taxonomy-version")

    def test_missing_required_field_fails(self):
        entry = valid_entry()
        del entry["action"]
        self.assert_invalid(valid_payload([entry]), "required-fields")

    def test_extra_field_is_rejected(self):
        entry = valid_entry()
        entry["unexpected_field"] = "not allowed"
        self.assert_invalid(valid_payload([entry]), "required-fields")

    def test_optional_fields_default_when_omitted(self):
        entry = relaxed_entry()
        self.assertNotIn("proposal_bucket", entry)
        self.assertNotIn("destinations", entry)
        result = self.run_ledger(valid_payload([entry]), config=None)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_duplicate_block_id_fails(self):
        self.assert_invalid(
            valid_payload([valid_entry(), copy.deepcopy(valid_entry())]),
            "duplicate-block-id",
        )

    def test_quarantine_must_be_blocked_excluded_and_destinationless(self):
        entry = valid_entry()
        entry.update(
            {
                "class": "quarantine",
                "action": "placeholder",
                "review_state": "approved",
                "proposal_bucket": "safe",
                "destinations": ["team"],
            }
        )
        payload = valid_payload([entry])
        for rule in ("quarantine-review", "quarantine-bucket", "quarantine-destination"):
            with self.subTest(rule=rule):
                self.assert_invalid(payload, rule)

    def test_personal_must_be_excluded_and_destinationless(self):
        entry = valid_entry()
        entry.update(
            {
                "class": "personal",
                "action": "generalize",
                "review_state": "blocked",
                "proposal_bucket": "safe",
                "destinations": ["team"],
                "reason_codes": ["personal-data"],
            }
        )
        payload = valid_payload([entry])
        self.assert_invalid(payload, "personal-bucket")
        self.assert_invalid(payload, "personal-destination")

    def test_low_confidence_requires_individual_review(self):
        entry = valid_entry()
        entry["confidence"] = "low"
        payload = valid_payload([entry])
        self.assert_invalid(payload, "low-confidence-review")
        self.assert_invalid(payload, "borderline-bucket")

    def test_restricted_requires_sanitization_and_individual_review(self):
        entry = valid_entry()
        entry.update({"class": "restricted", "action": "keep", "reason_codes": ["internal-architecture"]})
        payload = valid_payload([entry])
        self.assert_invalid(payload, "restricted-action")
        self.assert_invalid(payload, "restricted-review")
        self.assert_invalid(payload, "restricted-bucket")

    def test_invalid_class_action_combination_fails(self):
        entry = valid_entry()
        entry.update(
            {
                "class": "quarantine",
                "action": "keep",
                "review_state": "blocked",
                "proposal_bucket": "excluded",
                "destinations": [],
                "reason_codes": ["credentials"],
            }
        )
        self.assert_invalid(valid_payload([entry]), "quarantine-action")

    def test_borderline_entry_cannot_enter_safe_bucket(self):
        entry = valid_entry()
        entry.update({"review_state": "borderline-review", "proposal_bucket": "safe"})
        self.assert_invalid(valid_payload([entry]), "borderline-bucket")

    def test_ledger_is_bound_to_exact_source_hash(self):
        result = self.run_ledger(valid_payload(), "00:01 Ada: Different source.\n")
        self.assertEqual(result.returncode, 2, result.stderr)
        rules = {error["rule"] for error in json.loads(result.stdout)["errors"]}
        self.assertIn("source-sha256", rules)

    def test_source_line_count_must_match(self):
        payload = valid_payload()
        payload["source_line_count"] = 2
        self.assert_invalid(payload, "source-line-count")

    def test_source_locator_must_be_strict_line_range(self):
        entry = valid_entry(source_locator="00:00-01:00")
        self.assert_invalid(valid_payload([entry]), "source-locator-format")

    def test_line_coverage_cannot_have_gaps(self):
        source_text = "line one\nline two\nline three\n"
        entries = [valid_entry("B001", "L1-L1"), valid_entry("B002", "L3-L3")]
        result = self.run_ledger(valid_payload(entries, source_text), source_text)
        self.assertEqual(result.returncode, 2, result.stderr)
        rules = {error["rule"] for error in json.loads(result.stdout)["errors"]}
        self.assertIn("source-coverage-gap", rules)

    def test_line_coverage_cannot_overlap(self):
        source_text = "line one\nline two\nline three\n"
        entries = [valid_entry("B001", "L1-L2"), valid_entry("B002", "L2-L3")]
        result = self.run_ledger(valid_payload(entries, source_text), source_text)
        self.assertEqual(result.returncode, 2, result.stderr)
        rules = {error["rule"] for error in json.loads(result.stdout)["errors"]}
        self.assertIn("source-coverage-overlap", rules)

    def test_line_coverage_must_reach_end_of_source(self):
        source_text = "line one\nline two\n"
        result = self.run_ledger(
            valid_payload([valid_entry("B001", "L1-L1")], source_text), source_text
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        rules = {error["rule"] for error in json.loads(result.stdout)["errors"]}
        self.assertIn("source-coverage-gap", rules)

    def test_block_ids_must_be_sequential(self):
        source_text = "line one\nline two\n"
        entries = [valid_entry("B001", "L1-L1"), valid_entry("B003", "L2-L2")]
        result = self.run_ledger(valid_payload(entries, source_text), source_text)
        self.assertEqual(result.returncode, 2, result.stderr)
        rules = {error["rule"] for error in json.loads(result.stdout)["errors"]}
        self.assertIn("block-sequence", rules)

    def test_reason_codes_use_controlled_vocabulary(self):
        entry = valid_entry()
        entry["reason_codes"] = ["made-up-reason"]
        self.assert_invalid(valid_payload([entry]), "reason-codes")

    def test_unhashable_reason_or_destination_values_fail_cleanly(self):
        entry = valid_entry()
        entry["reason_codes"] = [{"not": "scalar"}]
        entry["destinations"] = [{"not": "scalar"}]
        result = self.run_ledger(valid_payload([entry]))
        self.assertEqual(result.returncode, 2, result.stderr)
        body = json.loads(result.stdout)
        rules = {error["rule"] for error in body["errors"]}
        self.assertIn("reason-codes", rules)
        self.assertIn("destinations-value", rules)

    def test_non_scalar_enum_values_fail_cleanly(self):
        entry = valid_entry()
        entry["class"] = ["shareable"]
        entry["action"] = ["keep"]
        entry["confidence"] = ["high"]
        entry["review_state"] = ["approved"]
        entry["proposal_bucket"] = ["safe"]
        result = self.run_ledger(valid_payload([entry]))
        self.assertEqual(result.returncode, 2, result.stderr)
        body = json.loads(result.stdout)
        rules = {error["rule"] for error in body["errors"]}
        self.assertTrue(
            {
                "class-value",
                "action-value",
                "confidence-value",
                "review-state-value",
                "proposal-bucket-value",
            }.issubset(rules)
        )

    def test_reason_code_must_match_sensitivity_class(self):
        entry = valid_entry()
        entry["reason_codes"] = ["credentials"]
        self.assert_invalid(valid_payload([entry]), "reason-class")

    def test_medium_confidence_shareable_class_requires_individual_review(self):
        entry = valid_entry()
        entry.update(
            {
                "action": "generalize",
                "confidence": "medium",
                "review_state": "borderline-review",
                "proposal_bucket": "individual-review",
                "reason_codes": ["other-requires-review"],
            }
        )
        result = self.run_ledger(valid_payload([entry]))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_individual_review_requires_a_sanitizing_action(self):
        entry = valid_entry()
        entry.update(
            {
                "confidence": "medium",
                "review_state": "borderline-review",
                "proposal_bucket": "individual-review",
                "reason_codes": ["other-requires-review"],
            }
        )
        self.assert_invalid(valid_payload([entry]), "individual-review-action")

    def test_restricted_entry_can_be_deterministically_excluded(self):
        entry = valid_entry()
        entry.update(
            {
                "class": "restricted",
                "action": "omit",
                "review_state": "blocked",
                "proposal_bucket": "excluded",
                "reason_codes": ["internal-architecture"],
                "destinations": [],
            }
        )
        result = self.run_ledger(valid_payload([entry]), config=None)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_safe_bucket_requires_high_confidence(self):
        entry = valid_entry()
        entry["confidence"] = "medium"
        self.assert_invalid(valid_payload([entry]), "safe-confidence")

    # --- Config-driven behaviour: taxonomy version and share destinations ---

    def test_ledger_accepted_with_no_destinations_configured_using_relaxation(self):
        entry = relaxed_entry()
        result = self.run_ledger(valid_payload([entry]), config=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"status": "valid"})

    def test_ledger_rejected_when_destination_not_configured(self):
        entry = relaxed_entry()
        entry["destinations"] = ["team"]
        result = self.run_ledger(valid_payload([entry]), config=None)
        self.assertEqual(result.returncode, 2, result.stderr)
        rules = {error["rule"] for error in json.loads(result.stdout)["errors"]}
        self.assertIn("destinations-value", rules)

    def test_ledger_accepted_when_temp_config_defines_team_destination(self):
        result = self.run_ledger(valid_payload(), config=TEAM_CONFIG)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"status": "valid"})

    def test_explicit_config_flag_is_honored(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger = Path(tmp_dir) / "ledger.json"
            source = Path(tmp_dir) / "transcript.txt"
            ledger.write_text(json.dumps(valid_payload()), encoding="utf-8")
            source.write_text(SOURCE_TEXT, encoding="utf-8")
            other_dir = Path(tmp_dir) / "elsewhere"
            other_dir.mkdir()
            config_path = other_dir / "custom.config.json"
            config_path.write_text(json.dumps(TEAM_CONFIG), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(ledger),
                    "--source",
                    str(source),
                    "--config",
                    str(config_path),
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=tmp_dir,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_config_flag_missing_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger = Path(tmp_dir) / "ledger.json"
            source = Path(tmp_dir) / "transcript.txt"
            ledger.write_text(json.dumps(valid_payload()), encoding="utf-8")
            source.write_text(SOURCE_TEXT, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(ledger),
                    "--source",
                    str(source),
                    "--config",
                    str(Path(tmp_dir) / "missing.config.json"),
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=tmp_dir,
            )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            json.loads(result.stdout), {"error": "config-unreadable", "status": "error"}
        )

    # --- Content-free guarantee ---

    def test_output_never_echoes_injected_value_in_invalid_fields(self):
        injected = "sk_live_51H8N9lookslikeatoken000000"
        entry = valid_entry(source_locator=injected)
        result = self.run_ledger(valid_payload([entry]))
        self.assertEqual(result.returncode, 2, result.stderr)
        body = json.loads(result.stdout)
        self.assertIn("source-locator-format", {error["rule"] for error in body["errors"]})
        self.assertNotIn(injected, result.stdout)
        self.assertNotIn(injected, result.stderr)


if __name__ == "__main__":
    unittest.main()
