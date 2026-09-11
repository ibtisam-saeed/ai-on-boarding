"""A deterministic backstop against a finding's own text disclosing a real secret -
independent of whether a subagent followed its "never quote secret values"
instruction. See openspec/changes/add-pr-review-agent/design.md - Decision 3 and the
first "Risks" entry, and the spec's "Never disclose secret values in a finding"
requirement.
"""
from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key_id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "generic_secret_assignment": re.compile(
        r"(?i)\b[A-Za-z0-9_]*(api[_-]?key|secret|token|password|passwd|pwd)[A-Za-z0-9_]*\b"
        r"\s*[:=]\s*['\"]([^'\"\s]{8,})['\"]"
    ),
}


def scan(text: str) -> list[str]:
    """Names of the patterns that matched somewhere in `text`."""
    return [name for name, pattern in _PATTERNS.items() if pattern.search(text)]


def redact(text: str) -> tuple[str, list[str]]:
    """Returns (redacted_text, pattern_names_matched). Leaves `text` unchanged, with
    an empty match list, when nothing matches.
    """
    matched: list[str] = []
    redacted = text
    for name, pattern in _PATTERNS.items():
        if pattern.search(redacted):
            matched.append(name)
            redacted = pattern.sub(REDACTED, redacted)
    return redacted, matched
