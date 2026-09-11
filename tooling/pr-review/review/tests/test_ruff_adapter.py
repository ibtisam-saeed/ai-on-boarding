"""Tests for review.ruff_adapter, written from the pr-review spec's "Post lint
violations as inline comments" requirement: a non-autofixable violation on a
changed line becomes a finding; a safely-autofixable one does not.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from review.ruff_adapter import convert  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "ruff_sample.json"


def _load_violations():
    return json.loads(FIXTURE.read_text())


def test_safely_autofixable_violation_produces_no_finding():
    violations = _load_violations()
    findings = convert(violations, repo_root="/repo")
    codes = [f.title.split(":")[0] for f in findings]
    assert "I001" not in codes  # applicability: safe - skipped


def test_non_fixable_violation_produces_a_finding():
    violations = _load_violations()
    findings = convert(violations, repo_root="/repo")
    ruf012 = next(f for f in findings if f.title.startswith("RUF012"))
    assert ruf012.file == "sdd_django_demo/api/mcp_views.py"
    assert ruf012.line == 40
    assert ruf012.category == "code-quality"
    assert ruf012.source == "ruff"
    assert "mutable-class-default" in ruf012.explanation


def test_unsafe_fix_still_produces_a_finding():
    """Only a *safe* fix is skipped - an unsafe one still needs a human's attention,
    so it must not be silently dropped just because a fix object is present.
    """
    violations = _load_violations()
    findings = convert(violations, repo_root="/repo")
    codes = [f.title.split(":")[0] for f in findings]
    assert "F841" in codes


def test_file_paths_are_made_relative_to_repo_root():
    violations = _load_violations()
    findings = convert(violations, repo_root="/repo")
    for finding in findings:
        assert not finding.file.startswith("/")
