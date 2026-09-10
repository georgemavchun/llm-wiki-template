#!/usr/bin/env python3
"""Detect likely quarantine content without echoing matched values.

Scans one or more files (or standard input) for secrets, high-risk
identifiers, explicit no-record phrases, control-bypass language, and
untrusted-instruction patterns. Output never contains a matched value, a
source line's text, or anything beyond categories, reason codes, line
numbers, file paths, hashes and counts.

An owner-approved allowlist (configured at ``privacy.allowlist`` in
``wiki.config.json``, or given via ``--allowlist``) lets one specific finding
in one specific file pass, once an owner records its path, exact sha256, and
reason code(s) in the allowlist JSON file. A finding is only ever suppressed
while the file's current text still hashes to the recorded value; any other
change re-blocks it. Use ``--no-allowlist`` to ignore the allowlist entirely
(for CI auditing), and ``--path-hint`` with ``--stdin`` to consult it for
piped text (this is what ``scripts/hooks/guard_write.py`` uses via
``scan_text_for_path``). See ``load_allowlist``, ``find_config`` and
``allowed_findings`` for the public helpers; an invalid allowlist file fails
the whole run (status ``error``, exit 1) rather than being silently ignored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True, order=True)
class Finding:
    category: str
    reason_code: str
    line: int


class AllowlistError(Exception):
    """Raised when a configured or explicit allowlist file exists but is malformed."""


PATTERNS = (
    (
        "credentials",
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", re.I),
    ),
    (
        "credentials",
        "credential-connection-string",
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|mssql)://"
            r"[^\s:/]+:[^@\s]+@",
            re.I,
        ),
    ),
    (
        "credentials",
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
    (
        "credentials",
        "bearer-token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b", re.I),
    ),
    (
        "credentials",
        "known-secret-token",
        re.compile(
            r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|"
            r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
            r"\bgithub_pat_[A-Za-z0-9_]{20,}\b|"
            r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b|"
            r"\bsk_live_[A-Za-z0-9]{16,}\b"
        ),
    ),
    (
        "credentials",
        "labelled-secret",
        re.compile(
            r"\b(?:password|passwd|api[_ -]?key|client[_ -]?secret|access[_ -]?token|"
            r"refresh[_ -]?token|webhook[_ -]?secret)\b\s*(?:is|[:=])\s*[\"']?"
            r"(?!(?:\[REDACTED\]|<REDACTED>|REDACTED|REMOVED|OMITTED|PLACEHOLDER)"
            r"(?:[\"']?[.,;)]?(?:\s|$)))"
            r"[^\s\"']{8,}",
            re.I,
        ),
    ),
    (
        "credentials",
        "labelled-recovery-material",
        re.compile(
            r"\b(?:seed|recovery|mnemonic)\s+(?:phrase|words?)\b\s*(?:is|[:=])\s*"
            r"(?:[A-Za-z]{3,}\s+){3,}[A-Za-z]{3,}\b|"
            r"\brecovery\s+codes?\b\s*(?:are|[:=])\s*[A-Z0-9][A-Z0-9 -]{11,}",
            re.I,
        ),
    ),
    (
        "high-risk-identifier",
        "labelled-high-risk-identifier",
        re.compile(
            r"\b(?:passport|national[_ -]?id|residence[_ -]?permit|tax[_ -]?id|"
            r"social[_ -]?security|ssn|cpr)\s*(?:number|no\.?)?\s*[:=]\s*"
            r"[A-Z0-9][A-Z0-9 -]{5,}",
            re.I,
        ),
    ),
    (
        "high-risk-identifier",
        "card-security-code",
        re.compile(r"\b(?:cvv|cvc)\s*[:=]\s*\d{3,4}\b", re.I),
    ),
    (
        "explicit-no-record",
        "explicit-no-record-en",
        re.compile(
            r"\b(?:off the record|do not write (?:this|that) down|don't write (?:this|that) down|"
            r"do not put (?:this|that) in (?:the )?notes|keep (?:this|that) between us|"
            r"do not tell anyone)\b",
            re.I,
        ),
    ),
    (
        "explicit-no-record",
        "explicit-no-record-ru",
        re.compile(r"(?:никому не говори|между нами|не записывай|не записывать|не заноси)", re.I),
    ),
    (
        "explicit-no-record",
        "explicit-no-record-da",
        re.compile(r"\b(?:skriv ikke dette ned|mellem os|fortæl det ikke til nogen)\b", re.I),
    ),
    (
        "control-bypass",
        "control-bypass",
        re.compile(
            r"\b(?:bypass|evade|circumvent|disable)\b.{0,80}"
            r"\b(?:aml|kyc|sanctions?|fraud|alert|detection|security|control|threshold|monitoring)\b|"
            r"\b(?:aml|kyc|sanctions?|fraud|alert|detection|security|control|threshold|monitoring)\b"
            r".{0,80}\b(?:bypass|evade|circumvent|disable)\b",
            re.I,
        ),
    ),
    (
        "untrusted-instruction",
        "prompt-injection",
        re.compile(
            r"\b(?:ignore|disregard|override)\b.{0,80}"
            r"\b(?:previous|prior|system|developer)\b.{0,40}\binstructions?\b",
            re.I,
        ),
    ),
    (
        "untrusted-instruction",
        "exfiltration-instruction",
        re.compile(
            r"\b(?:upload|send|post|paste|forward)\b.{0,100}"
            r"\b(?:passwords?|credentials?|secrets?|tokens?|api[_ -]?(?:keys?|tokens?)|"
            r"private[_ -]?keys?)\b|"
            r"\b(?:passwords?|credentials?|secrets?|tokens?|api[_ -]?(?:keys?|tokens?)|"
            r"private[_ -]?keys?)\b.{0,100}\b(?:upload|send|post|paste|forward)\b",
            re.I,
        ),
    ),
)

PAN_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
IBAN_CANDIDATE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b", re.I)
MULTILINE_REASON_CODES = {
    "explicit-no-record-en",
    "explicit-no-record-ru",
    "explicit-no-record-da",
    "control-bypass",
    "prompt-injection",
    "exfiltration-instruction",
}

# File extensions treated as binary; never blocked, always skipped.
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".zip",
    ".docx",
    ".xlsx",
    ".pptx",
    ".mp3",
    ".mp4",
    ".wav",
}

STDIN_LABEL = "<stdin>"


def luhn_valid(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def iban_valid(value: str) -> bool:
    compact = re.sub(r"\s+", "", value).upper()
    if not 15 <= len(compact) <= 34 or not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", compact):
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(ord(char) - 55) if char.isalpha() else char for char in rearranged)
    remainder = 0
    for char in numeric:
        remainder = (remainder * 10 + int(char)) % 97
    return remainder == 1


def scan_text(text: str) -> list[Finding]:
    """Scan text and return sorted, deduplicated findings. Never returns matched values."""
    findings: set[Finding] = set()
    lines = [unicodedata.normalize("NFKC", line) for line in text.splitlines()]
    for line_number, line in enumerate(lines, start=1):
        for category, reason_code, pattern in PATTERNS:
            if pattern.search(line):
                findings.add(Finding(category, reason_code, line_number))
        for match in PAN_CANDIDATE.finditer(line):
            if luhn_valid(match.group(0)):
                findings.add(Finding("high-risk-identifier", "payment-card-pan", line_number))
        for match in IBAN_CANDIDATE.finditer(line):
            if iban_valid(match.group(0)):
                findings.add(Finding("high-risk-identifier", "iban", line_number))
    for index, (first_line, second_line) in enumerate(zip(lines, lines[1:]), start=1):
        window = f"{first_line} {second_line}"
        for category, reason_code, pattern in PATTERNS:
            if reason_code not in MULTILINE_REASON_CODES:
                continue
            if pattern.search(first_line) or pattern.search(second_line):
                continue
            if pattern.search(window):
                findings.add(Finding(category, reason_code, index))
    return sorted(findings)


def source_binding(text: str) -> dict[str, object]:
    return {
        "line_count": len(text.splitlines()),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def is_binary_path(path: Path) -> bool:
    return path.suffix.lower() in BINARY_EXTENSIONS


def is_binary_bytes(raw: bytes) -> bool:
    return b"\x00" in raw[:8192]


def scan_file(path: str) -> dict[str, object]:
    """Scan a single file path (or STDIN_LABEL to mean pre-read stdin content is unsupported here).

    Returns a per-file record: {"path": ..., "status": ..., "findings": [...], "source": {...}?}.
    """
    file_path = Path(path)

    if is_binary_path(file_path):
        return {"path": path, "status": "skipped", "findings": []}

    try:
        raw = file_path.read_bytes()
    except OSError:
        return {"path": path, "status": "error", "findings": []}

    if is_binary_bytes(raw):
        return {"path": path, "status": "skipped", "findings": []}

    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return {"path": path, "status": "error", "findings": []}

    if not text.strip():
        # Nothing to scan (a .gitkeep, an empty placeholder). Skipped, not an
        # error: an empty file cannot leak anything, and the pre-commit hook
        # must not fail a commit that merely adds one.
        return {"path": path, "status": "skipped", "findings": []}

    findings = scan_text(text)
    status = "blocked" if findings else "pass"
    record: dict[str, object] = {
        "path": path,
        "status": status,
        "findings": [asdict(item) for item in findings],
        "source": source_binding(text),
    }
    return record


def scan_stdin_text(text: str) -> dict[str, object]:
    if not text.strip():
        return {"path": STDIN_LABEL, "status": "error", "findings": []}
    findings = scan_text(text)
    status = "blocked" if findings else "pass"
    return {
        "path": STDIN_LABEL,
        "status": status,
        "findings": [asdict(item) for item in findings],
        "source": source_binding(text),
    }


def find_config(start_dirs: Iterable[Path]) -> Optional[Path]:
    """Walk upward from each of ``start_dirs`` (in the order given) looking for
    a ``wiki.config.json``. Returns the first match found, or ``None`` if none
    of the start directories (or their ancestors) contain one.
    """
    visited: set[Path] = set()
    for start in start_dirs:
        try:
            current = Path(start).resolve()
        except OSError:
            continue
        while current not in visited:
            visited.add(current)
            candidate = current / "wiki.config.json"
            if candidate.is_file():
                return candidate
            parent = current.parent
            if parent == current:
                break
            current = parent
    return None


def _configured_allowlist_path(config_path: Path) -> Optional[Path]:
    """Read ``privacy.allowlist`` from ``config_path`` and resolve it relative
    to the config file's directory. Returns ``None`` if unset or the config
    itself cannot be read/parsed (that is not this function's error to raise).
    """
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    privacy = data.get("privacy")
    if not isinstance(privacy, dict):
        return None
    configured = privacy.get("allowlist")
    if not isinstance(configured, str) or not configured:
        return None
    return (config_path.parent / configured).resolve()


_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_ALLOWLIST_REQUIRED_ENTRY_FIELDS = ("path", "sha256", "reason_codes", "approved_by", "date")


def load_allowlist(path: Path) -> dict:
    """Load and validate an owner-approved allowlist JSON file.

    Raises ``AllowlistError`` naming ``path`` and the structural problem if the
    file is not valid JSON or does not match the documented schema (a
    ``schema_version: 1`` object with an ``entries`` list of path/sha256/
    reason_codes/approved_by/date records). Never includes the file's contents
    in the error message. Callers should only invoke this when the path is
    known to exist; absence of the file is not an error condition here.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AllowlistError(f"cannot read allowlist file {path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise AllowlistError(f"allowlist file {path} is not valid JSON") from exc

    if not isinstance(data, dict):
        raise AllowlistError(f"allowlist file {path} must contain a JSON object")

    if data.get("schema_version") != 1:
        raise AllowlistError(f"allowlist file {path} has a missing or unsupported schema_version")

    entries = data.get("entries")
    if not isinstance(entries, list):
        raise AllowlistError(f"allowlist file {path} must have an 'entries' list")

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise AllowlistError(f"allowlist file {path}: entries[{index}] must be an object")
        for field in _ALLOWLIST_REQUIRED_ENTRY_FIELDS:
            if field not in entry:
                raise AllowlistError(
                    f"allowlist file {path}: entries[{index}] is missing required field '{field}'"
                )
        if not isinstance(entry["path"], str) or not entry["path"]:
            raise AllowlistError(f"allowlist file {path}: entries[{index}].path must be a non-empty string")
        if not isinstance(entry["sha256"], str) or not _SHA256_HEX.match(entry["sha256"]):
            raise AllowlistError(
                f"allowlist file {path}: entries[{index}].sha256 must be 64 lowercase hex characters"
            )
        reason_codes = entry["reason_codes"]
        if not isinstance(reason_codes, list) or not reason_codes or not all(
            isinstance(code, str) and code for code in reason_codes
        ):
            raise AllowlistError(
                f"allowlist file {path}: entries[{index}].reason_codes must be a non-empty list of strings"
            )
        if not isinstance(entry["approved_by"], str) or not entry["approved_by"]:
            raise AllowlistError(
                f"allowlist file {path}: entries[{index}].approved_by must be a non-empty string"
            )
        if not isinstance(entry["date"], str) or not entry["date"]:
            raise AllowlistError(f"allowlist file {path}: entries[{index}].date must be a non-empty string")
        if "note" in entry and not isinstance(entry["note"], str):
            raise AllowlistError(f"allowlist file {path}: entries[{index}].note must be a string")

    return data


def allowed_findings(
    findings: list[Finding], relative_path: str, text: str, allowlist: Optional[dict]
) -> tuple[list[Finding], list[Finding]]:
    """Split ``findings`` into ``(kept, allowed)`` using ``allowlist`` entries.

    A finding is allowed when some entry's ``path`` equals ``relative_path``
    exactly, that entry's ``sha256`` equals the sha256 of ``text``, and the
    finding's ``reason_code`` is in that entry's ``reason_codes``. ``allowlist``
    may be ``None`` or empty, in which case nothing is allowed.
    """
    if not allowlist or not findings:
        return list(findings), []

    text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    allowed_reason_codes: set[str] = set()
    for entry in allowlist.get("entries", []):
        if entry.get("path") != relative_path:
            continue
        if entry.get("sha256") != text_sha:
            continue
        allowed_reason_codes.update(entry.get("reason_codes", []))

    kept: list[Finding] = []
    allowed: list[Finding] = []
    for finding in findings:
        if finding.reason_code in allowed_reason_codes:
            allowed.append(finding)
        else:
            kept.append(finding)
    return kept, allowed


def _resolve_relative_path(path: str, config_dir: Path) -> Optional[str]:
    """Return ``path`` resolved and made relative to ``config_dir``, POSIX-style."""
    try:
        resolved = Path(path).resolve()
        return resolved.relative_to(Path(config_dir).resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _apply_allowlist_to_record(
    record: dict, path: str, text: str, config_dir: Path, allowlist: Optional[dict]
) -> dict:
    """Mutate-and-return a scan record, moving allowlisted findings to ``allowed``.

    Matches against both the path exactly as given and the path resolved and
    made relative to ``config_dir``, per the allowlist matching rule. A record
    with no remaining findings becomes ``status: pass``.
    """
    if not allowlist or record["status"] != "blocked":
        return record

    findings = [
        Finding(item["category"], item["reason_code"], item["line"]) for item in record["findings"]
    ]
    kept, allowed = allowed_findings(findings, path, text, allowlist)

    resolved_relative = _resolve_relative_path(path, config_dir)
    if resolved_relative is not None and resolved_relative != path:
        kept, extra_allowed = allowed_findings(kept, resolved_relative, text, allowlist)
        allowed = allowed + extra_allowed

    record["findings"] = [asdict(item) for item in sorted(kept)]
    record["status"] = "blocked" if kept else "pass"
    if allowed:
        record["allowed"] = [asdict(item) for item in sorted(allowed)]
    return record


def scan_text_for_path(
    text: str,
    path: str,
    project_dir: Path,
    allowlist_path: Optional[Path] = None,
    use_allowlist: bool = True,
) -> dict:
    """Scan ``text`` as though it were the file at ``path`` and apply the
    owner-approved allowlist configured near ``project_dir`` (or the explicit
    ``allowlist_path``), so an owner-approved file can be rewritten with
    identical content without being re-blocked. ``path`` need not exist on
    disk (this is how ``--stdin --path-hint`` and ``guard_write.py`` use it).

    Returns a record shaped like :func:`scan_file`'s — ``path``, ``status``,
    ``findings``, ``source`` — plus an ``allowed`` field when the allowlist
    removed one or more findings. Raises ``AllowlistError`` if an allowlist
    file is found (configured or explicit) but is malformed; callers that want
    fail-open behavior (like the write guard) should let that propagate to
    their own top-level error handling.
    """
    findings = scan_text(text)
    record: dict = {
        "path": path,
        "status": "blocked" if findings else "pass",
        "findings": [asdict(item) for item in findings],
        "source": source_binding(text),
    }
    if not use_allowlist or record["status"] != "blocked":
        return record

    search_dirs = [Path(project_dir)]
    try:
        search_dirs.append(Path(path).resolve().parent)
    except OSError:
        pass
    config_path = find_config(search_dirs)
    config_dir = config_path.parent if config_path else Path(project_dir)

    resolved_allowlist_path = allowlist_path
    if resolved_allowlist_path is None and config_path is not None:
        resolved_allowlist_path = _configured_allowlist_path(config_path)

    if resolved_allowlist_path is None or not Path(resolved_allowlist_path).exists():
        return record

    allowlist = load_allowlist(resolved_allowlist_path)
    return _apply_allowlist_to_record(record, path, text, config_dir, allowlist)


def _read_text_quietly(path: str) -> Optional[str]:
    try:
        return Path(path).read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        return None


def _discover_allowlist(args: argparse.Namespace) -> tuple[Path, Optional[dict]]:
    """Resolve the config directory and load the effective allowlist for a CLI run.

    Honors ``--no-allowlist`` (disables entirely) and ``--allowlist`` (overrides
    the configured path). Raises ``AllowlistError`` if an allowlist file exists
    but is malformed; absence of the file is never an error.
    """
    if args.no_allowlist:
        return Path.cwd(), None

    search_dirs = [Path.cwd()]
    for file_path in args.files:
        try:
            search_dirs.append(Path(file_path).resolve().parent)
        except OSError:
            continue
    if args.path_hint:
        try:
            search_dirs.append(Path(args.path_hint).resolve().parent)
        except OSError:
            pass

    config_path = find_config(search_dirs)
    config_dir = config_path.parent if config_path else Path.cwd()

    allowlist_path: Optional[Path]
    if args.allowlist:
        allowlist_path = Path(args.allowlist)
    elif config_path is not None:
        allowlist_path = _configured_allowlist_path(config_path)
    else:
        allowlist_path = None

    if allowlist_path is None or not allowlist_path.exists():
        return config_dir, None

    return config_dir, load_allowlist(allowlist_path)


def overall_status(records: list[dict[str, object]]) -> str:
    statuses = {record["status"] for record in records}
    if "blocked" in statuses:
        return "blocked"
    if "error" in statuses:
        return "error"
    return "pass"


def render_json(overall: str, records: list[dict[str, object]]) -> str:
    payload = {"status": overall, "files": records}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def render_text(overall: str, records: list[dict[str, object]], quiet: bool) -> str:
    lines: list[str] = []
    if not quiet:
        lines.append(f"privacy preflight: {overall}")
    for record in records:
        status = record["status"]
        if quiet and status not in ("blocked", "error"):
            continue
        allowed = record.get("allowed") or []
        if status == "pass" and allowed:
            lines.append(f"- {record['path']}: pass ({len(allowed)} allowed by allowlist)")
        else:
            lines.append(f"- {record['path']}: {status}")
        if status == "blocked":
            for finding in record["findings"]:
                lines.append(
                    f"  - line {finding['line']}: {finding['category']}/{finding['reason_code']}"
                )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scan files (or stdin) for privacy quarantine content without disclosing matches. "
            "An owner-approved allowlist (wiki.config.json's privacy.allowlist, or --allowlist) "
            "can suppress one recorded finding for one file once its exact sha256 and reason "
            "code are on record; any other change to the file re-blocks it. Use --no-allowlist "
            "to ignore it, e.g. for a CI audit run."
        )
    )
    parser.add_argument("files", nargs="*", help="File paths to scan.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--quiet", action="store_true", help="Print only blocked and error files.")
    parser.add_argument(
        "--stdin", action="store_true", help="Also scan standard input as '<stdin>'."
    )
    parser.add_argument(
        "--allowlist",
        metavar="PATH",
        help="Override the configured privacy.allowlist path.",
    )
    parser.add_argument(
        "--no-allowlist",
        action="store_true",
        help="Ignore any allowlist, configured or explicit (e.g. for CI auditing).",
    )
    parser.add_argument(
        "--path-hint",
        metavar="RELATIVE_PATH",
        help="With --stdin, consult the allowlist as if stdin's text were this file.",
    )
    args = parser.parse_args(argv)

    if args.path_hint and not args.stdin:
        parser.error("--path-hint may only be used with --stdin")
    if args.allowlist and args.no_allowlist:
        parser.error("--allowlist and --no-allowlist are mutually exclusive")

    try:
        config_dir, allowlist = _discover_allowlist(args)
    except AllowlistError as exc:
        print(f"privacy preflight: {exc}", file=sys.stderr)
        return 1

    records: list[dict[str, object]] = []
    for path in args.files:
        record = scan_file(path)
        if allowlist and record["status"] == "blocked":
            text = _read_text_quietly(path)
            if text is not None:
                record = _apply_allowlist_to_record(record, path, text, config_dir, allowlist)
        records.append(record)

    if args.stdin:
        stdin_text = sys.stdin.read()
        record = scan_stdin_text(stdin_text)
        if allowlist and args.path_hint and record["status"] == "blocked":
            record = _apply_allowlist_to_record(
                record, args.path_hint, stdin_text, config_dir, allowlist
            )
        records.append(record)

    if not records:
        parser.error("no input: provide at least one FILE or use --stdin")

    overall = overall_status(records)

    if args.format == "json":
        print(render_json(overall, records))
    else:
        output = render_text(overall, records, args.quiet)
        if output:
            print(output)

    if overall == "blocked":
        return 2
    if overall == "error":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
