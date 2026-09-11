## Why

Pull requests in this repository get no automated review feedback today - there is no lint
check wired into CI at all, and any deeper review (security, architecture, performance, code
quality) only happens if a human does it by hand. Claude Code Action and Claude Code's
model-per-subagent mechanism now make it practical to offer a structured, multi-angle review on
request, without forcing every PR through an expensive AI review it may not need.

## What Changes

- Ruff runs automatically on every pull request as a deterministic CI check (no model call
  involved). Non-autofixable violations on lines the PR actually changed are also posted as
  individual inline PR review comments; autofixable violations are left to the failing check
  itself.
- A repository collaborator can request an AI-assisted review by commenting `@claude` (optionally
  naming a concern, e.g. "review this for security") on a pull request. Comments from non-
  collaborators do not trigger anything.
- Four specialised review skills exist - security, architecture, optimization, code quality -
  each running on a specific Claude model (security and architecture on Opus, optimization on
  Sonnet, code quality on Haiku). Only the skills relevant to the request and to the files the
  PR touches run; the system does not run all four on every request.
- Relevant skills run concurrently rather than one after another.
- Every finding, from Ruff or from a Claude skill, is posted as its own inline PR review comment
  attached to the relevant file and line whenever the position is part of the diff; a finding
  that cannot be pinned to a changed line is posted as a general PR comment instead. Findings are
  never merged into a single combined comment, and a finding from one skill is never folded into
  another skill's comment.
- One short summary comment/review is added per AI-assisted review run, naming which skills ran
  and how many findings were posted - it does not repeat the findings themselves.
- The same underlying issue identified more than once (by Ruff and a skill, by two skills, or by
  a repeated run after new commits) is posted once, not once per source.
- No finding, regardless of severity, blocks merge in this iteration - both the Ruff check and
  the AI-assisted review are advisory on top of Ruff's own pass/fail CI status.
- Delivered in three independently testable phases (deterministic publishing core, then Ruff
  integration, then the Claude-assisted review) rather than as one change, so each phase can be
  verified against a real pull request before the next is built.

## Capabilities

### New Capabilities
- `pr-review`: automated deterministic (Ruff) and on-demand AI-assisted (Claude, via `@claude`)
  review feedback, surfaced as individually isolated inline comments on a GitHub pull request.

### Modified Capabilities
(none - this change is fully additive and does not alter the behaviour of any existing capability)

## Impact

- New GitHub Actions workflows: automatic Ruff CI, and an `@claude`-triggered review workflow
  authenticated with a Claude Code OAuth token (a new repository secret).
- New `tooling/pr-review/` Python package: the deterministic publishing pipeline (finding
  validation, duplicate detection, GitHub comment/review creation) shared by both the Ruff path
  and the Claude-assisted path.
- New Claude Code skills (`.claude/skills/`) and subagents (`.claude/agents/`) defining the four
  review skills and the shared safety/output rules they follow.
- The Ruff workflow requires `pull-requests: write` permission on its GitHub token, a change from
  a read-only CI check.
- No changes to `sdd_django_demo/` application code or its existing specs.
