"""Tests for review.diff, written from the pr-review spec.

- "Post each finding as its own isolated comment" (the inline case) and "Fall back to
  a general comment for unattachable findings" both depend on correctly telling which
  (file, line) positions a pull request's diff actually makes available.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from review.diff import PullRequestContext, valid_positions  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample_patch.txt"


def test_added_and_context_lines_are_valid_positions():
    patch = FIXTURE.read_text()
    assert valid_positions(patch) == {10, 11, 12, 13, 14, 15}


def test_removed_lines_are_never_valid_positions():
    patch = "@@ -1,3 +1,2 @@\n line_a\n-removed_line\n line_b\n"
    assert valid_positions(patch) == {1, 2}


def test_no_newline_marker_does_not_advance_position():
    patch = "@@ -1,1 +1,1 @@\n+only_line\n\\ No newline at end of file\n"
    assert valid_positions(patch) == {1}


def test_pull_request_context_reports_invalid_position_outside_diff():
    ctx = PullRequestContext(
        owner="o", repo="r", number=1, commit_id="sha", file_positions={"a.py": {10, 11}}
    )
    assert ctx.is_valid_position("a.py", 10) is True
    assert ctx.is_valid_position("a.py", 99) is False
    assert ctx.is_valid_position("b.py", 10) is False
    assert ctx.is_valid_position("a.py", None) is False
