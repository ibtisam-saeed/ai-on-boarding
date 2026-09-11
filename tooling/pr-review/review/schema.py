"""The finding contract every source (Ruff, a review skill) must produce, and the
identity used to recognise a finding already posted on a pull request.

See openspec/changes/add-pr-review-agent/design.md - Decisions 1 and 5.
"""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["security", "architecture", "optimization", "code-quality"]
Severity = Literal["blocker", "major", "minor", "info"]

SEVERITY_RANK: dict[Severity, int] = {"blocker": 3, "major": 2, "minor": 1, "info": 0}


class Finding(BaseModel):
    category: Category
    severity: Severity
    file: str = Field(default="", description="Repo-relative path, empty if not file-specific.")
    line: int | None = Field(default=None, description="1-indexed line in the PR's new file version.")
    title: str
    explanation: str
    suggested_fix: str = ""
    source: str = Field(
        description="What produced this finding - 'ruff', or a skill name such as 'security-review'."
    )


class Findings(BaseModel):
    findings: list[Finding]


def fingerprint(finding: Finding) -> str:
    """Identity used to recognise a finding already posted on a pull request.

    Deliberately excludes `source`: the same underlying issue re-surfacing from a
    different source should still be recognised as already handled. It does include
    `category`, so a genuinely different concern at the same location (see the spec's
    "Suppress duplicate findings" requirement) is not mistaken for a repeat.
    """
    key = f"{finding.file}|{finding.line}|{finding.category}|{finding.title.strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
