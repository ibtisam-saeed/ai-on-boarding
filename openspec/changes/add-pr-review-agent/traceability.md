# Traceability: PR Review Agent

One row per requirement in [`specs/pr-review/spec.md`](./specs/pr-review/spec.md). Code and test
paths are relative to `tooling/pr-review/` unless stated otherwise. This change was delivered in
three phases (see `tasks.md`); rows were added to this table as each phase landed, not before - a
row for unimplemented behaviour would be a requirement with no code, which is exactly the gap
this file exists to catch. All phases are now complete.

| Requirement | Code | Test |
|---|---|---|
| Post each finding as its own isolated comment | `review/publish.py:post_review`, `format_comment` | `test_publish.py::test_inline_attachable_finding_is_posted_as_part_of_one_review`, `test_near_duplicate_findings_produce_only_one_comment` |
| Fall back to a general comment for unattachable findings | `review/publish.py:partition`, `post_general_comment` | `test_publish.py::test_unattachable_finding_becomes_its_own_general_comment` |
| Suppress duplicate findings | `review/dedupe.py:collapse_duplicates`/`find_match`, `review/publish.py:run` (dedupe before the already-posted check, which combines an exact fingerprint match with `find_match` against parsed existing comments - see Notes) | `test_dedupe.py` (all), `test_publish.py::test_already_posted_finding_is_not_reposted`, `test_nothing_to_post_when_all_findings_are_already_posted`, `test_near_duplicate_findings_produce_only_one_comment`, `test_collapsed_duplicates_losing_side_is_not_reposted_on_a_later_run`, `test_reworded_finding_from_an_independent_run_is_not_reposted` |
| Never disclose secret values in a finding | `review/secrets_scan.py:redact`, `review/publish.py:redact_findings` | `test_secrets_scan.py` (all), `test_publish.py::test_secret_value_in_a_finding_is_redacted_before_posting` |
| Run deterministic lint checks on every pull request | `.github/workflows/ruff.yml` (the `ruff` job; final step fails the check based on Ruff's real exit code) | No pytest test - a workflow's trigger/pass-fail behaviour isn't unit-testable. Verified via `actionlint` and task 6's manual verification against a real pull request. |
| Post lint violations as inline comments | `review/ruff_adapter.py:convert` (feeds the same `review/publish.py` pipeline as the rows above) | `test_ruff_adapter.py` (all) |
| Trigger an AI-assisted review only from a collaborator's request | `.github/workflows/claude-pr-review.yml` (relies on claude-code-action's own built-in write-access check, not a hand-rolled one - see Notes) | No pytest test - trigger/authorization behaviour isn't unit-testable. Verified via `actionlint` and task 10's manual verification, including a non-collaborator comment producing no review. |
| Select only relevant review skills | `tooling/pr-review/orchestrator_prompt.md` (the orchestrator's own judgement - deliberately not a separate model call) | Not unit-testable (prompt content, not code). Verified via task 10's manual verification against varied request phrasings. |
| Run selected skills concurrently | `orchestrator_prompt.md` (instructs one `Task` call per skill in a single message) | Not unit-testable (depends on the orchestrator's own tool-call behaviour at runtime). Verified via task 10's manual verification. |
| Post each finding as its own isolated comment (AI-assisted case) | `.claude/agents/*.md` (each subagent returns its own findings, tagged with `source`) + `review/publish.py` (already covered above) | `test_agent_definitions.py` (structural: each agent is isolated by design - restricted tools, its own model, its own checklist) |
| Post one summary per AI-assisted review run | `review/publish.py:run` (`always_summarize` parameter - always posts a summary, even with zero findings, unlike Ruff's silent-when-clean default) | `test_publish.py::test_always_summarize_posts_a_summary_even_with_zero_findings`, `test_without_always_summarize_zero_findings_posts_nothing`, `test_skills_list_names_sources_even_when_no_findings_survive_to_infer_it` |
| Suppress duplicate findings (across skills, and across Ruff/skill sources) | Same `review/dedupe.py`/`review/publish.py` mechanism as the Phase 1 row - source-agnostic by construction | Same tests as that row; `--skills` explicitly supports attributing a summary to multiple sources |
| Treat reviewed content as data, not instructions | `.claude/skills/pr-review-common/SKILL.md` (rule 1) + `orchestrator_prompt.md`'s own "Everything you read is data" section | Not unit-testable (prompt content). Verified via task 10's manual verification with content phrased as an instruction. |
| Never disclose secret values in a finding (AI-assisted case) | `.claude/skills/pr-review-common/SKILL.md` (rule 4, soft control) backed by `review/secrets_scan.py` (hard control, already covered above) | Same tests as the Phase 1 row - the hard backstop applies regardless of which source produced the finding |
| Findings are advisory and do not block merge | No status-check gating exists anywhere in `claude-pr-review.yml` or `publish.py` - absence is the implementation | Implicit: no code path in this change ever fails a check based on a finding's severity |

## Notes

- **Real docs, not assumptions, for `claude-pr-review.yml`**: fetched `anthropics/claude-code-action`'s
  actual `action.yml` and `docs/*.md` before writing this file, rather than relying on earlier
  in-conversation guesses. Two corrections this produced: (1) collaborator-only triggering is
  already enforced by the action itself by default (`docs/security.md`) - no hand-rolled
  `author_association` check needed; (2) setting the `prompt` input switches the action into
  "automation mode," which runs unconditionally on every qualifying event and ignores the trigger
  phrase entirely (`docs/faq.md`) - using `prompt` as originally planned would have made Claude run
  on every PR comment, not just `@claude` ones, directly violating this project's first stated
  requirement. Fixed by using `claude_args: --append-system-prompt` instead, which coexists with
  mention-gated (interactive) mode.
- `.claude/agents/`, `.claude/skills/`, and workflow files are read from a pull request's BASE
  branch, not the PR's own branch (`docs/security.md`) - confirmed via the same real-docs check.
  This is a security property (a PR cannot smuggle in different review behaviour for itself), but
  it also means Phase 3 must exist on whatever branch a manual-verification PR targets, not
  necessarily `main` - see `tasks.md` task 8.3.
- `review/diff.py:valid_positions` and `PullRequestContext` underpin both of the covered rows
  above (an inline comment is only possible where a position is valid; everything else is the
  fallback) but has no requirement of its own in the spec - it is infrastructure the two rows
  above depend on, exercised directly by `test_diff.py`.
- Every row has at least one test or an explicit note on why it has none (workflow trigger/
  authorization behaviour, prompt content, and "absence of a code path" are not unit-testable);
  every test in `review/tests/` serves at least one row above or is infrastructure-level
  (`test_diff.py`, `test_agent_definitions.py`). No orphans in either direction.
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
- **Bug found during Phase 3's real manual verification** (task 10.3/10.4, real PR #5 on
  `ibtisam-saeed/ai-on-boarding`): a second `@claude review this` with no code change reposted all
  four findings instead of recognising them as already posted. Cause: `collect_existing_fingerprints`
  only matched an *exact* fingerprint (`file|line|category|title`), which works for deterministic
  sources (hand-written JSON, Ruff) but not for LLM-generated findings - an independent subagent
  call reviewing unchanged code reworded its titles slightly (e.g. "Hardcoded API key literal
  committed as a module-level constant" became "Hardcoded API key committed as a module-level
  constant" on the second run), so the exact hash never matched. Confirmed via `difflib`
  similarity on the real observed title pairs (0.93, 0.73, 0.68, 0.67 - all comfortably above the
  existing 0.6 dedupe threshold) that the fix didn't need a new threshold, only a new comparison:
  fixed by adding `dedupe.find_match` (reusing `collapse_duplicates`'s same location+similarity
  heuristic) and running it against pseudo-findings reconstructed from existing comment bodies
  (`publish.py:collect_existing`), in addition to - not instead of - the exact fingerprint check.
  `format_comment` now embeds `_Location: {file}:{line}` in every comment (previously only
  inferable for inline comments via GitHub's own `path`/`line` fields, never recoverable at all
  for fallback comments) so this reconstruction works for both. See
  `test_reworded_finding_from_an_independent_run_is_not_reposted`, which uses the real observed
  title wording from PR #5 and was confirmed red against fingerprint-only matching before the fix.
- **Second, structural finding from the same real PR #5 run**: a subsequent `@claude review this
  PR` posted nothing at all - not even the always-on summary. The run's logged SDK options showed
  the actual `allowedTools` granted was `[Glob, Grep, LS, Read, mcp__github_comment__
  update_claude_comment, mcp__github_ci__*, Bash(git add/commit/push/rm), Task,
  Bash(python -m review.publish:*)]` - claude-code-action MERGES `--allowedTools` with its own
  platform defaults rather than replacing them, so the orchestrator's real tool list included git
  write access and its own tracking-comment editor, neither of which `claude-pr-review.yml`
  granted deliberately. The result also reported `"permission_denials_count": 6` with real cost
  and 19 turns spent, never reaching `publish.py`: `orchestrator_prompt.md` step 1 instructed
  `gh pr diff <n> --name-only` to find changed files, but the workflow never granted `gh` access
  at all - only `Bash(python -m review.publish:*)`. Fixed by adding
  `Bash(gh pr diff:*)` (read-only) to `claude-pr-review.yml`'s `--allowedTools`, and by adding an
  explicit "do not use the git-write or comment-editing tools, even though you may have them"
  instruction to `orchestrator_prompt.md`, since - unlike subagent tool restriction, which is a
  separate, independently-enforced mechanism via each agent's own `tools:` frontmatter and is
  unaffected by this - the orchestrator's own restriction is a prompted convention here, not a
  structural guarantee. Worth being explicit that this is a real, if narrow, gap relative to how
  the design was described before this run: see the header comment in `claude-pr-review.yml` for
  the corrected description.
