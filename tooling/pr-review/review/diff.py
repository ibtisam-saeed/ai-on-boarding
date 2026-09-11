"""Talks to the GitHub API for the publishing pipeline: fetches a pull request's diff
and resolves which (file, line) positions are valid targets for an inline review
comment. `github_get`/`github_post` are also the HTTP helpers `publish.py` uses to
fetch existing comments and post new ones, so there is one place that knows how to
authenticate to GitHub, not several.

See openspec/changes/add-pr-review-agent/design.md - Decision 6, and the spec's
"Fall back to a general comment for unattachable findings" requirement.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import requests

API_ROOT = "https://api.github.com"


class GitHubError(RuntimeError):
    """A GitHub API call did not succeed."""


def _token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise GitHubError("GITHUB_TOKEN is not set - required to call the GitHub API.")
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_get(path: str, params: dict | None = None) -> list | dict:
    """GET against the GitHub API, following pagination for list responses."""
    url = f"{API_ROOT}{path}"
    results: list = []
    while url:
        response = requests.get(url, headers=_headers(), params=params, timeout=30)
        if response.status_code >= 400:
            raise GitHubError(f"GET {path} failed: {response.status_code} {response.text}")
        payload = response.json()
        if not isinstance(payload, list):
            return payload
        results.extend(payload)
        url = response.links.get("next", {}).get("url")
        params = None  # the next URL already carries the query string
    return results


def github_post(path: str, json: dict) -> dict:
    url = f"{API_ROOT}{path}"
    response = requests.post(url, headers=_headers(), json=json, timeout=30)
    if response.status_code >= 400:
        raise GitHubError(f"POST {path} failed: {response.status_code} {response.text}")
    return response.json()


_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def valid_positions(patch: str) -> set[int]:
    """The new-file line numbers a patch's hunks make available for an inline comment.

    Mirrors what GitHub's review-comment API accepts as a position: any line the diff
    shows on the right-hand (new) side - added or unchanged context - but not a line
    that only existed on the old side, and not a "no newline at end of file" marker.
    """
    positions: set[int] = set()
    new_line = 0
    for raw_line in patch.splitlines():
        header = _HUNK_HEADER.match(raw_line)
        if header:
            new_line = int(header.group(1))
            continue
        if new_line == 0:
            continue
        if raw_line.startswith("-") or raw_line.startswith("\\"):
            continue
        positions.add(new_line)
        new_line += 1
    return positions


@dataclass
class PullRequestContext:
    owner: str
    repo: str
    number: int
    commit_id: str
    file_positions: dict[str, set[int]] = field(default_factory=dict)

    def is_valid_position(self, path: str, line: int | None) -> bool:
        if line is None:
            return False
        return line in self.file_positions.get(path, set())


def fetch_pull_request_context(owner: str, repo: str, number: int) -> PullRequestContext:
    pr = github_get(f"/repos/{owner}/{repo}/pulls/{number}")
    files = github_get(f"/repos/{owner}/{repo}/pulls/{number}/files", params={"per_page": 100})
    file_positions = {
        entry["filename"]: valid_positions(entry["patch"])
        for entry in files
        if entry.get("patch")
    }
    return PullRequestContext(
        owner=owner,
        repo=repo,
        number=number,
        commit_id=pr["head"]["sha"],
        file_positions=file_positions,
    )
