#!/usr/bin/env python3
"""Detect likely quarantine content without echoing matched values.

Scans one or more files (or standard input) for secrets, high-risk
identifiers, explicit no-record phrases, control-bypass language, and
untrusted-instruction patterns. Output never contains a matched value, a
source line's text, or anything beyond categories, reason codes, line
numbers, file paths, hashes and counts.
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


@dataclass(frozen=True, order=True)
class Finding:
    category: str
    reason_code: str
    line: int


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
        return {"path": path, "status": "error", "findings": []}

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
        lines.append(f"- {record['path']}: {status}")
        if status == "blocked":
            for finding in record["findings"]:
                lines.append(
                    f"  - line {finding['line']}: {finding['category']}/{finding['reason_code']}"
                )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan files (or stdin) for privacy quarantine content without disclosing matches."
    )
    parser.add_argument("files", nargs="*", help="File paths to scan.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--quiet", action="store_true", help="Print only blocked and error files.")
    parser.add_argument(
        "--stdin", action="store_true", help="Also scan standard input as '<stdin>'."
    )
    args = parser.parse_args(argv)

    records: list[dict[str, object]] = []
    for path in args.files:
        records.append(scan_file(path))

    if args.stdin:
        stdin_text = sys.stdin.read()
        records.append(scan_stdin_text(stdin_text))

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
