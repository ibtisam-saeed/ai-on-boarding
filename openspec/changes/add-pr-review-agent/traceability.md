# Traceability: PR Review Agent

One row per requirement in [`specs/pr-review/spec.md`](./specs/pr-review/spec.md) that Phase 1
implements. Code and test paths are relative to `tooling/pr-review/`. This change is delivered in
three phases (see `tasks.md`); requirements covered by Phase 2 and Phase 3 are added to this table
as those phases land, not before - a row for unimplemented behaviour would be a requirement with
no code, which is exactly the gap this file exists to catch.

| Requirement | Code | Test |
|---|---|---|
| Post each finding as its own isolated comment | `review/publish.py:post_review`, `format_comment` | `test_publish.py::test_inline_attachable_finding_is_posted_as_part_of_one_review`, `test_near_duplicate_findings_produce_only_one_comment` |
| Fall back to a general comment for unattachable findings | `review/publish.py:partition`, `post_general_comment` | `test_publish.py::test_unattachable_finding_becomes_its_own_general_comment` |
| Suppress duplicate findings | `review/dedupe.py:collapse_duplicates`, `review/publish.py:run` (dedupe *before* the fingerprint skip - see Notes) | `test_dedupe.py` (all), `test_publish.py::test_already_posted_finding_is_not_reposted`, `test_nothing_to_post_when_all_findings_are_already_posted`, `test_near_duplicate_findings_produce_only_one_comment`, `test_collapsed_duplicates_losing_side_is_not_reposted_on_a_later_run` |
| Never disclose secret values in a finding | `review/secrets_scan.py:redact`, `review/publish.py:redact_findings` | `test_secrets_scan.py` (all), `test_publish.py::test_secret_value_in_a_finding_is_redacted_before_posting` |
| Run deterministic lint checks on every pull request | `.github/workflows/ruff.yml` (the `ruff` job; final step fails the check based on Ruff's real exit code) | No pytest test - a workflow's trigger/pass-fail behaviour isn't unit-testable. Verified via `actionlint` and task 6's manual verification against a real pull request. |
| Post lint violations as inline comments | `review/ruff_adapter.py:convert` (feeds the same `review/publish.py` pipeline as the rows above) | `test_ruff_adapter.py` (all) |

## Notes

- Not yet covered (Phase 3): collaborator-only triggering, skill selection, concurrent execution,
  one summary per AI-assisted run, content-not-instructions, findings-are-advisory - depend on the
  skills, subagents, orchestrator, and trigger workflow, not built yet.
- `review/diff.py:valid_positions` and `PullRequestContext` underpin both of the covered rows
  above (an inline comment is only possible where a position is valid; everything else is the
  fallback) but has no requirement of its own in the spec - it is infrastructure the two rows
  above depend on, exercised directly by `test_diff.py`.
- Every row has at least one test; every test in `review/tests/` serves at least one row above or
  is infrastructure-level (`test_diff.py`). No orphans in either direction for what Phase 1 covers.
- **Bug found during manual verification** (task 3.1, real PR #3 on `ibtisam-saeed/ai-on-boarding`):
  `run()` originally checked each candidate's fingerprint against already-posted comments *before*
  deduping. A collapsed duplicate's losing side is never individually posted, so its own
  fingerprint was never recorded - only the survivor's was. On a second run with the same input,
  the loser passed the "already posted" check (it had never been posted under its own identity)
  and was posted fresh, as if new. Fixed by deduping first, then checking the survivor's
  fingerprint - see `test_collapsed_duplicates_losing_side_is_not_reposted_on_a_later_run`, which
  reproduces the exact scenario and was confirmed red against the original ordering before the fix.
- **Scope correction found while setting up Phase 2's manual verification** (task 6): the first
  version of `ruff.yml` ran `ruff check sdd_django_demo` unscoped - since this repo already has 14
  pre-existing violations, every PR (regardless of what it touched) would have produced roughly
  10 fallback general comments about unrelated code. Fixed by scoping Ruff to the PR's actual
  changed Python files (via `gh pr diff --name-only`) before running it, so `publish.py`'s
  fallback path is only ever exercised for its intended case - a touched file, an untouched line -
  not "file the PR never touched at all."
