"""Tests for review.publish, written from the pr-review spec: isolated inline comments,
the fallback for unattachable findings, one summary per run, and duplicate suppression
(both within a batch and against what a pull request already carries). No test in this
file makes a real network call - the GitHub API is faked.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

import pytest  # noqa: E402

from review import diff as diff_module  # noqa: E402
from review import publish as publish_module  # noqa: E402
from review.schema import Finding, fingerprint  # noqa: E402


class FakeGitHub:
    def __init__(self, files=None):
        self.files = files or []
        self.review_comments: list[dict] = []
        self.issue_comments: list[dict] = []
        self.posted_reviews: list[dict] = []
        self.posted_review_comments: list[dict] = []
        self.fail_review = False

    def get(self, path, params=None):
        if path == "/repos/owner/repo/pulls/1":
            return {"head": {"sha": "deadbeef"}}
        if path == "/repos/owner/repo/pulls/1/files":
            return self.files
        if path == "/repos/owner/repo/pulls/1/comments":
            return self.review_comments
        if path == "/repos/owner/repo/issues/1/comments":
            return self.issue_comments
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, json):
        if path == "/repos/owner/repo/pulls/1/reviews":
            if self.fail_review:
                raise diff_module.GitHubError("boom")
            self.posted_reviews.append(json)
            return {}
        if path == "/repos/owner/repo/pulls/1/comments":
            self.posted_review_comments.append(json)
            return {}
        if path == "/repos/owner/repo/issues/1/comments":
            self.issue_comments.append(json)
            return {}
        raise AssertionError(f"unexpected POST {path}")


@pytest.fixture
def fake_github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(diff_module, "github_get", fake.get)
    monkeypatch.setattr(diff_module, "github_post", fake.post)
    monkeypatch.setattr(publish_module, "github_get", fake.get)
    monkeypatch.setattr(publish_module, "github_post", fake.post)
    return fake


def _write_findings(tmp_path, findings):
    path = tmp_path / "findings.json"
    path.write_text(json.dumps([f.model_dump() for f in findings]))
    return path


def test_inline_attachable_finding_is_posted_as_part_of_one_review(tmp_path, fake_github):
    fake_github.files = [{"filename": "a.py", "patch": "@@ -1,1 +1,2 @@\n line1\n+line2"}]
    finding = Finding(
        category="security", severity="major", file="a.py", line=2,
        title="Hardcoded secret", explanation="explains it", source="security-review",
    )
    path = _write_findings(tmp_path, [finding])

    publish_module.run("owner/repo", 1, path)

    assert len(fake_github.posted_reviews) == 1
    review = fake_github.posted_reviews[0]
    assert len(review["comments"]) == 1
    assert review["comments"][0]["path"] == "a.py"
    assert review["comments"][0]["line"] == 2
    assert "Automated review: 1 finding(s) posted." in review["body"]
    assert fake_github.issue_comments == []


def test_unattachable_finding_becomes_its_own_general_comment(tmp_path, fake_github):
    fake_github.files = []  # nothing in the diff, so no position is ever valid
    finding = Finding(
        category="architecture", severity="minor", file="b.py", line=5,
        title="Tight coupling", explanation="explains it", source="architecture-review",
    )
    path = _write_findings(tmp_path, [finding])

    publish_module.run("owner/repo", 1, path)

    assert fake_github.posted_reviews == []
    # one general comment for the summary, one for the unattachable finding
    assert len(fake_github.issue_comments) == 2
    bodies = [c["body"] for c in fake_github.issue_comments]
    assert any("Tight coupling" in b for b in bodies)
    assert any(b.startswith("Automated review:") for b in bodies)


def test_already_posted_finding_is_not_reposted(tmp_path, fake_github):
    finding = Finding(
        category="security", severity="major", file="a.py", line=1,
        title="Hardcoded secret", explanation="explains it", source="security-review",
    )
    fake_github.files = [{"filename": "a.py", "patch": "@@ -1,1 +1,1 @@\n line1"}]
    fake_github.issue_comments = [
        {"body": f"<!-- pr-review-fingerprint: {fingerprint(finding)} -->"}
    ]
    path = _write_findings(tmp_path, [finding])

    publish_module.run("owner/repo", 1, path)

    assert fake_github.posted_reviews == []
    assert fake_github.issue_comments == [
        {"body": f"<!-- pr-review-fingerprint: {fingerprint(finding)} -->"}
    ]


def test_near_duplicate_findings_produce_only_one_comment(tmp_path, fake_github):
    fake_github.files = [{"filename": "a.py", "patch": "@@ -1,1 +1,1 @@\n line1"}]
    a = Finding(
        category="security", severity="major", file="a.py", line=1,
        title="Hardcoded secret in a.py", explanation="e1", source="security-review",
    )
    b = Finding(
        category="code-quality", severity="minor", file="a.py", line=1,
        title="Hardcoded secret found in a.py", explanation="e2", source="code-quality",
    )
    path = _write_findings(tmp_path, [a, b])

    publish_module.run("owner/repo", 1, path)

    assert len(fake_github.posted_reviews) == 1
    assert len(fake_github.posted_reviews[0]["comments"]) == 1


def test_secret_value_in_a_finding_is_redacted_before_posting(tmp_path, fake_github):
    fake_github.files = [{"filename": "settings.py", "patch": "@@ -1,1 +1,1 @@\n line1"}]
    finding = Finding(
        category="security", severity="blocker", file="settings.py", line=1,
        title="Hardcoded AWS key",
        explanation="Found AKIAABCDEFGHIJKLMNOP hardcoded in settings.py",
        source="security-review",
    )
    path = _write_findings(tmp_path, [finding])

    publish_module.run("owner/repo", 1, path)

    body = fake_github.posted_reviews[0]["comments"][0]["body"]
    assert "AKIAABCDEFGHIJKLMNOP" not in body
    assert "[REDACTED]" in body


def test_collapsed_duplicates_losing_side_is_not_reposted_on_a_later_run(tmp_path, fake_github):
    """Regression test for a bug found during manual verification (real PR #3 on
    ibtisam-saeed/ai-on-boarding): a duplicate's losing side was never individually
    fingerprinted, since only the survivor gets posted - so a second run re-posted the
    loser as if it were a brand new finding. Dedupe must happen before the
    already-posted fingerprint check, not after.
    """
    fake_github.files = [{"filename": "a.py", "patch": "@@ -1,1 +1,1 @@\n line1"}]
    a = Finding(
        category="code-quality", severity="minor", file="a.py", line=1,
        title="Hardcoded secret found in a.py", explanation="e1", source="code-quality",
    )
    b = Finding(
        category="security", severity="major", file="a.py", line=1,
        title="Hardcoded secret in a.py", explanation="e2", source="security-review",
    )
    path = _write_findings(tmp_path, [a, b])

    publish_module.run("owner/repo", 1, path)
    assert len(fake_github.posted_reviews) == 1
    assert len(fake_github.posted_reviews[0]["comments"]) == 1

    # Simulate GitHub now carrying what was just posted, as a second run would see it.
    fake_github.review_comments = [
        {"body": c["body"]} for c in fake_github.posted_reviews[0]["comments"]
    ]

    result = publish_module.run("owner/repo", 1, path)

    assert result == 0
    assert len(fake_github.posted_reviews) == 1  # no second review posted
    assert fake_github.issue_comments == []


def test_nothing_to_post_when_all_findings_are_already_posted(tmp_path, fake_github):
    finding = Finding(
        category="security", severity="major", file="a.py", line=1,
        title="Hardcoded secret", explanation="explains it", source="security-review",
    )
    fake_github.files = [{"filename": "a.py", "patch": "@@ -1,1 +1,1 @@\n line1"}]
    fake_github.review_comments = [
        {"body": f"<!-- pr-review-fingerprint: {fingerprint(finding)} -->"}
    ]
    path = _write_findings(tmp_path, [finding])

    result = publish_module.run("owner/repo", 1, path)

    assert result == 0
    assert fake_github.posted_reviews == []
    assert fake_github.issue_comments == []
