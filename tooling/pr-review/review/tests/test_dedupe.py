"""Tests for review.dedupe, written from the pr-review spec's "Suppress duplicate
findings" requirement: the same underlying issue found by more than one source
results in one comment; genuinely different concerns do not get merged away.

Includes a documented known limitation (see design.md's "Risks" entry on this
heuristic): fuzzy title matching is character-based, so two very differently worded
descriptions of the same real-world issue may not be recognised as duplicates. That
is asserted here as current behaviour, not silently assumed.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from review.dedupe import collapse_duplicates  # noqa: E402
from review.schema import Finding  # noqa: E402


def _finding(**overrides):
    base = dict(
        category="security",
        severity="major",
        file="settings.py",
        line=10,
        title="Hardcoded secret in settings.py",
        explanation="explanation",
        source="security-review",
    )
    base.update(overrides)
    return Finding(**base)


def test_near_identical_titles_at_the_same_location_collapse_to_one():
    a = _finding(title="Hardcoded secret in settings.py", source="security-review")
    b = _finding(title="Hardcoded secret found in settings.py", source="code-quality", severity="minor")
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 1


def test_duplicate_keeps_the_higher_severity_finding_and_notes_the_other_source():
    a = _finding(severity="minor", source="code-quality")
    b = _finding(severity="blocker", source="security-review")
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 1
    assert survivors[0].severity == "blocker"
    assert "code-quality" in survivors[0].explanation


def test_distinct_titles_at_the_same_location_are_not_merged():
    a = _finding(title="Hardcoded secret in settings.py")
    b = _finding(
        title="Function exceeds 200 lines and should be split",
        category="code-quality",
        source="code-quality",
    )
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 2


def test_same_title_at_a_different_file_is_not_merged():
    a = _finding(title="Hardcoded secret", file="settings.py")
    b = _finding(title="Hardcoded secret", file="other.py")
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 2


def test_same_title_far_apart_on_the_same_file_is_not_merged():
    a = _finding(title="Missing error handling", line=10)
    b = _finding(title="Missing error handling", line=200)
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 2


def test_known_limitation_very_differently_worded_duplicates_are_not_caught():
    """Same underlying issue, described in unrelated wording - the character-based
    fuzzy match does not catch this. Documented in design.md as a risk requiring
    tuning against real examples before this is trusted in production.
    """
    a = _finding(title="Hardcoded secret in settings.py")
    b = _finding(title="SECRET_KEY should not be committed to source", category="code-quality", source="code-quality")
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 2
