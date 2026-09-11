"""The only code path that ever writes a PR review comment. No model call happens
here - it is the deterministic half of the pipeline both the Ruff workflow and the
Claude-assisted orchestrator call after they have findings to report.

Run as: python -m review.publish --pr <n> --repo <owner/repo> --input <findings.json>
(--repo defaults to $GITHUB_REPOSITORY). Requires GITHUB_TOKEN in the environment.

See openspec/changes/add-pr-review-agent/design.md - Decisions 4, 5, 6, and the spec's
requirements on isolated comments, the unattachable-finding fallback, one summary per
run, duplicate suppression, and never disclosing secret values.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from review.dedupe import collapse_duplicates
from review.diff import (
    GitHubError,
    PullRequestContext,
    fetch_pull_request_context,
    github_get,
    github_post,
)
from review.schema import Finding, fingerprint
from review.secrets_scan import redact

FINGERPRINT_RE = re.compile(r"<!-- pr-review-fingerprint: ([0-9a-f]{16}) -->")

SEVERITY_LABEL = {
    "blocker": "\U0001f534 Blocker",
    "major": "\U0001f7e0 Major",
    "minor": "\U0001f7e1 Minor",
    "info": "ℹ️ Info",
}


def load_findings(path: Path) -> tuple[list[Finding], list[str]]:
    raw = json.loads(path.read_text())
    items = raw["findings"] if isinstance(raw, dict) and "findings" in raw else raw

    valid: list[Finding] = []
    warnings: list[str] = []
    for index, item in enumerate(items):
        try:
            valid.append(Finding.model_validate(item))
        except ValidationError as exc:
            warnings.append(f"finding[{index}] dropped - failed schema validation: {exc}")
    return valid, warnings


def collect_existing_fingerprints(ctx: PullRequestContext) -> set[str]:
    review_comments = github_get(
        f"/repos/{ctx.owner}/{ctx.repo}/pulls/{ctx.number}/comments", params={"per_page": 100}
    )
    issue_comments = github_get(
        f"/repos/{ctx.owner}/{ctx.repo}/issues/{ctx.number}/comments", params={"per_page": 100}
    )
    fingerprints: set[str] = set()
    for comment in list(review_comments) + list(issue_comments):
        fingerprints.update(FINGERPRINT_RE.findall(comment.get("body") or ""))
    return fingerprints


def redact_findings(findings: list[Finding]) -> list[Finding]:
    redacted: list[Finding] = []
    for finding in findings:
        title, title_hits = redact(finding.title)
        explanation, explanation_hits = redact(finding.explanation)
        suggested_fix, fix_hits = redact(finding.suggested_fix) if finding.suggested_fix else ("", [])
        if title_hits or explanation_hits or fix_hits:
            explanation += "\n\n_(A potential secret value in this finding was redacted before posting.)_"
        redacted.append(
            finding.model_copy(
                update={"title": title, "explanation": explanation, "suggested_fix": suggested_fix}
            )
        )
    return redacted


def partition(findings: list[Finding], ctx: PullRequestContext) -> tuple[list[Finding], list[Finding]]:
    inline, fallback = [], []
    for finding in findings:
        (inline if ctx.is_valid_position(finding.file, finding.line) else fallback).append(finding)
    return inline, fallback


def format_comment(finding: Finding) -> str:
    parts = [
        f"**{SEVERITY_LABEL[finding.severity]} - {finding.title}**",
        f"_Source: {finding.source}_",
        "",
        finding.explanation,
    ]
    if finding.suggested_fix:
        parts += ["", f"**Suggested fix:** {finding.suggested_fix}"]
    parts += ["", f"<!-- pr-review-fingerprint: {fingerprint(finding)} -->"]
    return "\n".join(parts)


def format_summary(
    total_posted: int, skipped_duplicates: int, skipped_already_posted: int, sources: list[str]
) -> str:
    lines = [f"Automated review: {total_posted} finding(s) posted."]
    if sources:
        lines.append(f"Sources: {', '.join(sources)}.")
    extra = []
    if skipped_duplicates:
        extra.append(f"{skipped_duplicates} duplicate(s) collapsed")
    if skipped_already_posted:
        extra.append(f"{skipped_already_posted} already posted and skipped")
    if extra:
        lines.append(" ".join(extra) + ".")
    return "\n".join(lines)


def post_general_comment(ctx: PullRequestContext, body: str) -> None:
    github_post(f"/repos/{ctx.owner}/{ctx.repo}/issues/{ctx.number}/comments", {"body": body})


def post_review(ctx: PullRequestContext, inline_findings: list[Finding], summary_body: str) -> None:
    comments = [
        {"path": f.file, "line": f.line, "side": "RIGHT", "body": format_comment(f)}
        for f in inline_findings
    ]
    payload = {
        "commit_id": ctx.commit_id,
        "event": "COMMENT",
        "body": summary_body,
        "comments": comments,
    }
    try:
        github_post(f"/repos/{ctx.owner}/{ctx.repo}/pulls/{ctx.number}/reviews", payload)
        return
    except GitHubError as exc:
        print(
            f"warning: batched review failed ({exc}); falling back to individual comments",
            file=sys.stderr,
        )

    # Defensive fallback (design.md, Decision 6): one call per comment, so a single bad
    # position doesn't lose every finding in the batch. A comment that still fails
    # becomes a general comment rather than being dropped.
    for finding in inline_findings:
        try:
            github_post(
                f"/repos/{ctx.owner}/{ctx.repo}/pulls/{ctx.number}/comments",
                {
                    "commit_id": ctx.commit_id,
                    "path": finding.file,
                    "line": finding.line,
                    "side": "RIGHT",
                    "body": format_comment(finding),
                },
            )
        except GitHubError as exc:
            print(
                f"warning: could not post inline comment for {finding.file}:{finding.line} "
                f"({exc}); posting as a general comment instead",
                file=sys.stderr,
            )
            post_general_comment(ctx, format_comment(finding))
    post_general_comment(ctx, summary_body)


def run(repo: str, pr_number: int, findings_path: Path) -> int:
    owner, repo_name = repo.split("/", 1)
    ctx = fetch_pull_request_context(owner, repo_name, pr_number)

    candidates, load_warnings = load_findings(findings_path)
    for warning in load_warnings:
        print(f"warning: {warning}", file=sys.stderr)

    # Dedupe BEFORE checking what's already posted. A collapsed duplicate's losing
    # side never gets its own fingerprint recorded (only the survivor's does, since
    # only the survivor is ever posted) - checking fingerprints first would let that
    # losing finding slip through as "new" on every later run, because it is never
    # individually recognised as already handled. See openspec/changes/
    # add-pr-review-agent/tasks.md task 3's manual verification, which caught this.
    deduped = collapse_duplicates(candidates)
    skipped_duplicates = len(candidates) - len(deduped)

    already_posted = collect_existing_fingerprints(ctx)
    new_candidates = [f for f in deduped if fingerprint(f) not in already_posted]
    skipped_already_posted = len(deduped) - len(new_candidates)

    final = redact_findings(new_candidates)
    inline, fallback = partition(final, ctx)

    if not inline and not fallback:
        print(
            f"Nothing to post - {skipped_already_posted} already posted, "
            f"{skipped_duplicates} duplicate(s) collapsed to zero new findings."
        )
        return 0

    sources = sorted({f.source for f in final})
    summary = format_summary(len(final), skipped_duplicates, skipped_already_posted, sources)

    if inline:
        post_review(ctx, inline, summary)
    else:
        post_general_comment(ctx, summary)

    for finding in fallback:
        post_general_comment(ctx, format_comment(finding))

    print(
        f"Posted {len(inline)} inline comment(s) and {len(fallback)} general comment(s); "
        f"skipped {skipped_duplicates} duplicate(s) and {skipped_already_posted} "
        "already-posted finding(s)."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True, help="Pull request number")
    parser.add_argument(
        "--repo", default=os.environ.get("GITHUB_REPOSITORY"), help="owner/repo, defaults to $GITHUB_REPOSITORY"
    )
    parser.add_argument("--input", type=Path, required=True, help="Findings JSON file")
    args = parser.parse_args(argv)

    if not args.repo:
        parser.error("--repo is required (or set GITHUB_REPOSITORY)")

    return run(args.repo, args.pr, args.input)


if __name__ == "__main__":
    raise SystemExit(main())
