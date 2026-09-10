#!/usr/bin/env python3
"""Validate a transcript privacy classification ledger without emitting source content.

The ledger is a content-free JSON record binding classification decisions to
exact line ranges of a source file. This validator checks structure, the
controlled vocabulary, per-class invariants, and deterministic source
coverage (no gaps, no overlaps, bound to an exact sha256 and line count).

Sensitivity classes (renamed from the underlying taxonomy for this template):
  quarantine  - never stored verbatim (was "quarantine-redact")
  personal    - never leaves this wiki (was "personal-only")
  restricted  - may reach a team wiki only with per-item approval (was "project-restricted")
  shareable   - may reach a team wiki after normal review (was "project-safe")

Taxonomy version and configured share destinations are read from
wiki.config.json (see load_config). When no destinations are configured,
`destinations` must be empty on every entry, and `shareable`/`restricted`
entries may use `proposal_bucket: excluded` with `review_state: approved`
and any action valid for their class -- meaning "nothing to propose" because
there is nowhere configured to send it. `personal` still requires
`review_state: blocked`; `quarantine` rules are unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_TAXONOMY_VERSION = "2026-09-10"
CONFIG_FILENAME = "wiki.config.json"

REQUIRED_FIELDS = {
    "block_id",
    "source_locator",
    "class",
    "action",
    "confidence",
    "review_state",
    "reason_codes",
}
OPTIONAL_FIELDS = {"proposal_bucket", "destinations"}
ALLOWED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

CLASSES = {"quarantine", "personal", "restricted", "shareable"}
ACTIONS = {"keep", "generalize", "anonymize", "aggregate", "omit", "placeholder"}
CONFIDENCE = {"high", "medium", "low"}
REVIEW_STATES = {"approved", "borderline-review", "blocked"}
PROPOSAL_BUCKETS = {"safe", "individual-review", "excluded"}

REASON_CODES = {
    "credentials",
    "high-risk-identifier",
    "explicit-no-record",
    "control-bypass",
    "prompt-injection",
    "exfiltration",
    "personal-data",
    "special-category",
    "criminal-offence",
    "hr-performance",
    "complaint-investigation",
    "compensation",
    "private-life",
    "internal-politics",
    "financial-crime",
    "regulatory-legal",
    "customer-confidentiality",
    "board-investor",
    "third-party-confidentiality",
    "internal-architecture",
    "security-resilience",
    "compliance-implementation",
    "roadmap-partnership",
    "planning-resourcing",
    "public-approved",
    "sanitized-technical",
    "sanitized-product-process",
    "sanitized-organizational",
    "small-universe",
    "harm-risk",
    "regulated-finance",
    "security-risk",
    "privilege-legal",
    "low-confidence",
    "other-requires-review",
}
QUARANTINE_REASON_CODES = {
    "credentials",
    "high-risk-identifier",
    "explicit-no-record",
    "control-bypass",
    "prompt-injection",
    "exfiltration",
}
PERSONAL_REASON_CODES = {
    "personal-data",
    "special-category",
    "criminal-offence",
    "hr-performance",
    "complaint-investigation",
    "compensation",
    "private-life",
    "internal-politics",
    "financial-crime",
    "regulatory-legal",
    "customer-confidentiality",
    "board-investor",
    "third-party-confidentiality",
}
RESTRICTED_REASON_CODES = {
    "internal-architecture",
    "security-resilience",
    "compliance-implementation",
    "roadmap-partnership",
    "planning-resourcing",
}
SHAREABLE_REASON_CODES = {
    "public-approved",
    "sanitized-technical",
    "sanitized-product-process",
    "sanitized-organizational",
}
CROSS_CUTTING_REASON_CODES = {
    "small-universe",
    "harm-risk",
    "regulated-finance",
    "security-risk",
    "privilege-legal",
    "low-confidence",
    "other-requires-review",
}
CLASS_REASON_CODES = {
    "quarantine": QUARANTINE_REASON_CODES | {"regulated-finance", "security-risk", "privilege-legal"},
    "personal": PERSONAL_REASON_CODES | CROSS_CUTTING_REASON_CODES,
    "restricted": RESTRICTED_REASON_CODES | CROSS_CUTTING_REASON_CODES,
    "shareable": SHAREABLE_REASON_CODES | CROSS_CUTTING_REASON_CODES,
}
RESTRICTED_ANY_ACTIONS = {"omit", "generalize", "anonymize", "aggregate"}
SHAREABLE_ANY_ACTIONS = {"keep", "generalize", "anonymize", "aggregate", "omit"}

LEDGER_FIELDS = {"taxonomy_version", "source_sha256", "source_line_count", "entries"}
SOURCE_LOCATOR = re.compile(r"L([1-9]\d*)-L([1-9]\d*)")


class ConfigError(Exception):
    """Raised when an explicitly requested --config path cannot be read/parsed."""


@dataclass(frozen=True, order=True)
class ValidationError:
    block_id: str
    rule: str


def _parse_config(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"taxonomy_version": DEFAULT_TAXONOMY_VERSION, "destinations": set()}
    privacy = data.get("privacy")
    privacy = privacy if isinstance(privacy, dict) else {}
    taxonomy_version = privacy.get("taxonomy_version", DEFAULT_TAXONOMY_VERSION)
    if not isinstance(taxonomy_version, str):
        taxonomy_version = DEFAULT_TAXONOMY_VERSION
    share = data.get("share")
    share = share if isinstance(share, dict) else {}
    destinations_map = share.get("destinations")
    destinations_map = destinations_map if isinstance(destinations_map, dict) else {}
    destinations = {key for key in destinations_map if isinstance(key, str)}
    return {"taxonomy_version": taxonomy_version, "destinations": destinations}


def load_config(config_path: str | None = None, ledger_path: str | None = None) -> dict[str, Any]:
    """Locate and load wiki.config.json.

    Precedence: an explicit --config path (raises ConfigError if unreadable);
    else walk up from the ledger's directory looking for wiki.config.json;
    else walk up from the current working directory; else defaults.
    """
    if config_path is not None:
        candidate = Path(config_path)
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigError("config-unreadable") from exc
        return _parse_config(data)

    search_starts = []
    if ledger_path is not None:
        search_starts.append(Path(ledger_path).resolve().parent)
    search_starts.append(Path.cwd())

    seen: set[Path] = set()
    for start in search_starts:
        current = start
        while True:
            if current not in seen:
                seen.add(current)
                candidate = current / CONFIG_FILENAME
                if candidate.is_file():
                    try:
                        data = json.loads(candidate.read_text(encoding="utf-8"))
                        return _parse_config(data)
                    except (OSError, UnicodeError, json.JSONDecodeError):
                        pass
            if current.parent == current:
                break
            current = current.parent

    return {"taxonomy_version": DEFAULT_TAXONOMY_VERSION, "destinations": set()}


def validate_ledger(
    payload: Any, source_text: str, config: dict[str, Any] | None = None
) -> list[ValidationError]:
    if config is None:
        config = {"taxonomy_version": DEFAULT_TAXONOMY_VERSION, "destinations": set()}
    taxonomy_version = config.get("taxonomy_version", DEFAULT_TAXONOMY_VERSION)
    destinations_configured: set[str] = set(config.get("destinations", set()))
    no_destinations_configured = not destinations_configured

    errors: set[ValidationError] = set()
    if not isinstance(payload, dict):
        return [ValidationError("$ledger", "ledger-object")]
    if set(payload) != LEDGER_FIELDS:
        errors.add(ValidationError("$ledger", "ledger-fields"))
    if payload.get("taxonomy_version") != taxonomy_version:
        errors.add(ValidationError("$ledger", "taxonomy-version"))
    actual_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    source_sha256 = payload.get("source_sha256")
    if (
        not isinstance(source_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", source_sha256)
        or source_sha256 != actual_sha256
    ):
        errors.add(ValidationError("$ledger", "source-sha256"))
    actual_line_count = len(source_text.splitlines())
    source_line_count = payload.get("source_line_count")
    if (
        isinstance(source_line_count, bool)
        or not isinstance(source_line_count, int)
        or source_line_count != actual_line_count
        or source_line_count < 1
    ):
        errors.add(ValidationError("$ledger", "source-line-count"))
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.add(ValidationError("$ledger", "entries-list"))
        return sorted(errors)

    seen_ids: set[str] = set()
    expected_line = 1
    for index, entry in enumerate(entries, start=1):
        fallback_id = f"$entry-{index}"
        if not isinstance(entry, dict):
            errors.add(ValidationError(fallback_id, "entry-object"))
            continue
        block_id = entry.get("block_id") if isinstance(entry.get("block_id"), str) else fallback_id
        field_set = set(entry)
        if not REQUIRED_FIELDS.issubset(field_set) or not field_set.issubset(ALLOWED_FIELDS):
            errors.add(ValidationError(block_id, "required-fields"))
        if block_id in seen_ids:
            errors.add(ValidationError(block_id, "duplicate-block-id"))
        seen_ids.add(block_id)
        if not isinstance(entry.get("block_id"), str) or not entry.get("block_id", "").strip():
            errors.add(ValidationError(block_id, "block-id"))
        if block_id != f"B{index:03d}":
            errors.add(ValidationError(block_id, "block-sequence"))
        source_locator = entry.get("source_locator")
        locator_match = (
            SOURCE_LOCATOR.fullmatch(source_locator)
            if isinstance(source_locator, str)
            else None
        )
        if locator_match is None:
            errors.add(ValidationError(block_id, "source-locator-format"))
        else:
            start_line, end_line = (int(value) for value in locator_match.groups())
            if end_line < start_line:
                errors.add(ValidationError(block_id, "source-locator-range"))
            else:
                if start_line > expected_line:
                    errors.add(ValidationError(block_id, "source-coverage-gap"))
                elif start_line < expected_line:
                    errors.add(ValidationError(block_id, "source-coverage-overlap"))
                expected_line = max(expected_line, end_line + 1)
                if end_line > actual_line_count:
                    errors.add(ValidationError(block_id, "source-locator-bounds"))

        sensitivity_class = entry.get("class")
        action = entry.get("action")
        confidence = entry.get("confidence")
        review_state = entry.get("review_state")
        proposal_bucket = entry.get("proposal_bucket", "excluded")
        reason_codes = entry.get("reason_codes")
        destinations = entry.get("destinations", [])

        if not isinstance(sensitivity_class, str) or sensitivity_class not in CLASSES:
            errors.add(ValidationError(block_id, "class-value"))
        if not isinstance(action, str) or action not in ACTIONS:
            errors.add(ValidationError(block_id, "action-value"))
        if not isinstance(confidence, str) or confidence not in CONFIDENCE:
            errors.add(ValidationError(block_id, "confidence-value"))
        if not isinstance(review_state, str) or review_state not in REVIEW_STATES:
            errors.add(ValidationError(block_id, "review-state-value"))
        if not isinstance(proposal_bucket, str) or proposal_bucket not in PROPOSAL_BUCKETS:
            errors.add(ValidationError(block_id, "proposal-bucket-value"))
        reason_codes_valid = (
            isinstance(reason_codes, list)
            and bool(reason_codes)
            and all(isinstance(code, str) for code in reason_codes)
        )
        if reason_codes_valid:
            reason_codes_valid = (
                len(reason_codes) == len(set(reason_codes))
                and all(code in REASON_CODES for code in reason_codes)
            )
        if not reason_codes_valid:
            errors.add(ValidationError(block_id, "reason-codes"))
        elif isinstance(sensitivity_class, str) and sensitivity_class in CLASS_REASON_CODES:
            allowed_reasons = CLASS_REASON_CODES[sensitivity_class]
            if not set(reason_codes).issubset(allowed_reasons):
                errors.add(ValidationError(block_id, "reason-class"))
            if proposal_bucket == "safe" and not set(reason_codes).issubset(
                SHAREABLE_REASON_CODES
            ):
                errors.add(ValidationError(block_id, "reason-class"))
        destinations_valid = (
            isinstance(destinations, list)
            and all(isinstance(destination, str) for destination in destinations)
        )
        if destinations_valid:
            destinations_valid = (
                len(destinations) == len(set(destinations))
                and all(destination in destinations_configured for destination in destinations)
            )
        if not destinations_valid:
            errors.add(ValidationError(block_id, "destinations-value"))
            destinations = []

        if sensitivity_class == "quarantine":
            if action not in {"omit", "placeholder"}:
                errors.add(ValidationError(block_id, "quarantine-action"))
            if review_state != "blocked":
                errors.add(ValidationError(block_id, "quarantine-review"))
            if proposal_bucket != "excluded":
                errors.add(ValidationError(block_id, "quarantine-bucket"))
            if destinations:
                errors.add(ValidationError(block_id, "quarantine-destination"))

        if sensitivity_class == "personal":
            if action not in {"omit", "generalize", "aggregate"}:
                errors.add(ValidationError(block_id, "personal-action"))
            if review_state != "blocked":
                errors.add(ValidationError(block_id, "personal-review"))
            if proposal_bucket != "excluded":
                errors.add(ValidationError(block_id, "personal-bucket"))
            if destinations:
                errors.add(ValidationError(block_id, "personal-destination"))

        if sensitivity_class == "restricted":
            if proposal_bucket == "excluded":
                relaxed = (
                    no_destinations_configured
                    and review_state == "approved"
                    and action in RESTRICTED_ANY_ACTIONS
                )
                if not relaxed:
                    if action != "omit":
                        errors.add(ValidationError(block_id, "restricted-excluded-action"))
                    if review_state != "blocked":
                        errors.add(ValidationError(block_id, "restricted-excluded-review"))
                if destinations:
                    errors.add(ValidationError(block_id, "restricted-excluded-destination"))
            else:
                if action not in {"generalize", "anonymize", "aggregate"}:
                    errors.add(ValidationError(block_id, "restricted-action"))
                if review_state != "borderline-review":
                    errors.add(ValidationError(block_id, "restricted-review"))
                if proposal_bucket != "individual-review":
                    errors.add(ValidationError(block_id, "restricted-bucket"))
                if not destinations:
                    errors.add(ValidationError(block_id, "restricted-destination"))

        if sensitivity_class == "shareable":
            if action not in SHAREABLE_ANY_ACTIONS:
                errors.add(ValidationError(block_id, "shareable-action"))
            if proposal_bucket == "excluded":
                relaxed = (
                    no_destinations_configured
                    and review_state == "approved"
                    and action in SHAREABLE_ANY_ACTIONS
                )
                if not relaxed:
                    if action != "omit":
                        errors.add(ValidationError(block_id, "shareable-excluded-action"))
                    if review_state != "blocked":
                        errors.add(ValidationError(block_id, "shareable-excluded-review"))
                if destinations:
                    errors.add(ValidationError(block_id, "shareable-excluded-destination"))

        if confidence == "low" and sensitivity_class in {"shareable", "restricted"}:
            if review_state != "borderline-review":
                errors.add(ValidationError(block_id, "low-confidence-review"))
            if proposal_bucket != "individual-review":
                errors.add(ValidationError(block_id, "borderline-bucket"))

        if review_state == "borderline-review" and proposal_bucket != "individual-review":
            errors.add(ValidationError(block_id, "borderline-bucket"))
        if proposal_bucket == "safe":
            if sensitivity_class != "shareable":
                errors.add(ValidationError(block_id, "safe-class"))
            if review_state != "approved":
                errors.add(ValidationError(block_id, "safe-review"))
            if confidence != "high":
                errors.add(ValidationError(block_id, "safe-confidence"))
            if not destinations:
                errors.add(ValidationError(block_id, "safe-destination"))
            if action in {"omit", "placeholder"}:
                errors.add(ValidationError(block_id, "safe-action"))
        if proposal_bucket == "individual-review":
            if review_state != "borderline-review":
                errors.add(ValidationError(block_id, "individual-review-state"))
            if not destinations:
                errors.add(ValidationError(block_id, "individual-review-destination"))
            if action not in {"generalize", "anonymize", "aggregate"}:
                errors.add(ValidationError(block_id, "individual-review-action"))

    if expected_line <= actual_line_count:
        errors.add(ValidationError("$ledger", "source-coverage-gap"))

    return sorted(errors)


def render(errors: list[ValidationError], output_format: str) -> str:
    if output_format == "json":
        if errors:
            return json.dumps(
                {"errors": [asdict(error) for error in errors], "status": "invalid"},
                sort_keys=True,
            )
        return json.dumps({"status": "valid"}, sort_keys=True)
    if not errors:
        return "privacy ledger: valid"
    lines = ["privacy ledger: invalid"]
    lines.extend(f"- {error.block_id}: {error.rule}" for error in errors)
    return "\n".join(lines)


def render_blocked(block_ids: list[str], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(
            {"blocked_blocks": block_ids, "status": "blocked"}, sort_keys=True
        )
    lines = ["privacy ledger: blocked"]
    lines.extend(f"- {block_id}: quarantine" for block_id in block_ids)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a transcript privacy ledger.")
    parser.add_argument("ledger")
    parser.add_argument("--source", required=True)
    parser.add_argument("--config")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        if args.format == "json":
            print(json.dumps({"error": "ledger-unreadable", "status": "error"}, sort_keys=True))
        else:
            print("privacy ledger: error (ledger-unreadable)")
        return 1

    try:
        source_text = Path(args.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        if args.format == "json":
            print(json.dumps({"error": "source-unreadable", "status": "error"}, sort_keys=True))
        else:
            print("privacy ledger: error (source-unreadable)")
        return 1

    try:
        config = load_config(args.config, args.ledger)
    except ConfigError:
        if args.format == "json":
            print(json.dumps({"error": "config-unreadable", "status": "error"}, sort_keys=True))
        else:
            print("privacy ledger: error (config-unreadable)")
        return 1

    errors = validate_ledger(payload, source_text, config)
    if errors:
        print(render(errors, args.format))
        return 2
    blocked_blocks = sorted(
        entry["block_id"]
        for entry in payload["entries"]
        if entry.get("class") == "quarantine"
    )
    if blocked_blocks:
        print(render_blocked(blocked_blocks, args.format))
        return 3
    print(render([], args.format))
    return 0


if __name__ == "__main__":
    sys.exit(main())
