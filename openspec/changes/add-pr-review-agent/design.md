## Context

See proposal.md - Why, What Changes. Relevant constraints not restated there: this repo has no
existing Claude Code Action usage, no lint tooling wired into CI, and no type checker configured
anywhere. The repository is public, so pull requests can come from untrusted contributors. The
existing local `/code-review` skill's "cite-or-nit, explicit verdict, at most two passes"
contract (`openspec/config.yaml`) governs a different, human-invoked review of OpenSpec
artifacts; this change is independent of it and does not gate merge (see the spec's "Findings
are advisory" requirement). Authentication for the AI-assisted path uses a Claude Code OAuth
token (subscription-based), not an Anthropic API key - this rules out the raw Anthropic API's
`output_format` structured-output feature, which is API-key-only.

## Goals / Non-Goals

**Goals:**
- Give each review skill its own pinned model and let selected skills run concurrently.
- Ensure nothing with the ability to call tools can post to GitHub itself - only one
  deterministic, non-model code path ever does.
- Make that publishing path source-agnostic, so the lint check and the AI-assisted skills share
  identical duplicate-detection and posting behaviour.
- Make review runs idempotent across repeated triggers without an arbitrary pass limit.
- Verify the riskiest, least-proven behaviours (subagent concurrency and Skill use inside a
  non-interactive Action run, the OAuth-token auth path, GitHub's acceptance of computed diff
  positions) against a real pull request before building further on top of them.

**Non-Goals:**
- Wiring any finding's severity into a required status check - findings are advisory only in
  this change (see Open Questions).
- Adding a type checker or a pull-request-triggered pytest run - out of scope for this change,
  left for separate future work.
- A hard, path-restricted sandbox for subagent tool use - accepted as infeasible to guarantee
  given static agent definitions cannot be parameterised per pull request; addressed with
  layered mitigations instead (see Risks).
- Automated evaluation of review quality/prompt tuning - relies on manual verification against a
  real pull request per phase, not an automated eval suite, in this change.

## Decisions

**1. Review skills are Claude Code subagents (`.claude/agents/*.md`), not directly-invoked
Skills and not raw Anthropic API calls.**
A plain Skill cannot pin a model and cannot give isolated, parallel execution - it only injects
instructions into whatever session invokes it. A raw Anthropic API call with a forced
`output_format` schema was considered, but that feature requires API-key auth incompatible with
the required OAuth-token path; once ruled out, a raw-call approach (via headless `claude -p`
subprocesses) offered no reliability advantage over subagents - both rely on prompted, not
enforced, JSON - while adding custom subprocess-orchestration code that the native `Task` tool
already provides, and losing the ability to `Read` files for real context. Subagents, dispatched
by the orchestrator via parallel `Task` calls, are the native mechanism for this pattern.

**2. Each subagent loads its rubric from a Skill it invokes for itself, rather than carrying the
rubric text in its own body.**
Separates the mechanism (agent definition: model + tools) from the content (skill: what to look
for). A shared `pr-review-common` skill, loaded by all four subagents, centralises the
content/instruction-separation rule, the diff-scope rule, the no-secrets rule, and the required
output format, so they are written once rather than duplicated across four files. Each skill
also has its own rubric skill (`security-review-checklist`, etc.).

**3. Subagents are restricted to `Read` and `Skill` only.**
No `Grep`/`Glob`, `Bash`, `Edit`, or `Write`. This is the requirement that a skill must never
post to GitHub itself, enforced by simply not granting any tool capable of it. The orchestrator
supplies an explicit list of the pull request's changed files in each dispatch, narrowing, though
not eliminating, the chance a misled subagent reads something outside that scope (see Risks).

**4. One deterministic, non-LLM publishing pipeline is the only code path that writes to GitHub,
and it is source-agnostic.**
Both the lint workflow and the orchestrator (after collecting subagent findings) call the same
publishing code. This keeps duplicate-detection and posting behaviour identical regardless of
source, and means the lint-to-comment path needs no model call at all - fully consistent with
selecting only relevant, necessary model calls elsewhere in this design.

**5. Duplicate/idempotency handling is content-addressed, not a run-count limit.**
Before posting, the publishing pipeline fingerprints each candidate finding (file, line,
category, title) and checks it against fingerprints already present on the pull request's
existing comments, skipping anything already posted. This converges naturally on repeated
triggers - a re-run only ever adds genuinely new findings - rather than borrowing the local
`/code-review` skill's two-pass limit, which exists to bound an open-ended human-read list and
does not fit a system that can check what it already posted.

**6. Findings are posted via one GitHub review call carrying multiple inline comments plus the
summary as its body, with a defensive per-comment fallback if the batch call fails.**
Atomic, avoids partial-post inconsistency, and gives the summary comment a natural home in the
same call. Comments grouped under one review remain individually anchored and independently
resolvable - the grouping is a cosmetic timeline detail, not a merge of comment content, so it
does not conflict with the requirement that findings stay isolated.

**7. Content read during a review is explicitly instructed to be treated as data, not commands.**
Applied in every subagent's shared skill and in the orchestrator's own instructions. A standard,
low-cost mitigation against prompt injection, reinforcing rather than replacing the harder
controls in Decisions 3 and 8.

**8. Only repository collaborators can trigger a review, and only one review runs per pull
request at a time.**
An `author_association` check in the trigger workflow, and a concurrency group keyed by pull
request number. This is the primary, hard-enforced control on both cost (subscription-based
OAuth usage) and on the injection/exfiltration risk surface in Decision 3 - it removes untrusted
external contributors from the population able to invoke a review at all.

**9. Delivered and verified in three phases - publishing core, then Ruff integration, then the
Claude-assisted skills - each manually verified against a real pull request before the next
phase's tasks begin.**
Several behaviours here are unverified against real infrastructure: subagent concurrency and
headless Skill use inside a non-interactive Action run, GitHub's actual acceptance of computed
diff positions, and the OAuth-token auth path in CI. Ordering phases from least to most dependent
on those unverified behaviours means a wrong assumption is caught, and only costs rework, within
the phase that exposed it.

## Risks / Trade-offs

[Risk] A `Read`-only subagent is not a hard, path-restricted sandbox - it could still be told,
via injected content, to read a sensitive file such as `.env` if it disregards its instructions.
→ Mitigation: an explicit orchestrator-supplied file allowlist and the content/instruction-
separation rule (soft controls), plus a deterministic secret-pattern scan over every finding's
text before it is ever posted (a hard backstop independent of subagent behaviour), plus
collaborator-only triggering, which limits who can attempt this at all.

[Risk] The duplicate-detection heuristic (location clustering plus fuzzy title matching) can
both under-merge differently worded descriptions of the same issue and over-merge unrelated
findings that share generic phrasing near each other.
→ Mitigation: validated against a curated fixture set of real near-duplicate and real
false-positive pairs in Phase 1's tests, before any production use.

[Risk] A skill's output is not guaranteed-valid JSON, since the OAuth-token auth path cannot use
the raw Anthropic API's enforced `output_format` feature.
→ Mitigation: a strict single-trailing-fenced-JSON-block output convention in every skill
prompt, schema validation on receipt, one retry on a parse failure, and dropping (with a logged
warning) a finding that still fails to parse.

[Risk] Subagent concurrency and headless Skill invocation inside a non-interactive GitHub
Actions run are assumed, not yet proven, behaviours.
→ Mitigation: Phase 3 is ordered last and manually verified against a real pull request before
being considered done; a wrong assumption here only requires reworking Phase 3.

[Risk] A large pull request could produce many lint violations or many skill findings, flooding
it with comments.
→ Mitigation: autofixable lint violations are never posted; skill findings are capped per skill
by severity; both paths share the same duplicate-suppression pipeline across repeated runs.

## Migration Plan

No existing behaviour is removed or altered, so there is no migration of existing data or
contracts. Rollout is the three-phase sequence itself:
- Phase 1 (publishing core) merges and is manually verified by invoking the publisher locally
  against a real pull request.
- Phase 2 (Ruff integration) merges and is manually verified with a real pull request carrying a
  real lint violation.
- Phase 3 (Claude-assisted skills) merges and is manually verified end-to-end with a real
  `@claude` request on a real pull request, including confirming a non-collaborator's comment
  does not trigger anything.

Each phase's manual verification is confirmed before the next phase's tasks begin. Rollback at
any point is a plain revert of that phase's files - no phase depends on irreversible external
state beyond the `CLAUDE_CODE_OAUTH_TOKEN` repository secret, which is additive and inert until
Phase 3's workflow exists.

## Open Questions

- Should a future iteration wire `severity: blocker` findings into a required status check?
  Left advisory-only for this change; revisiting this would need new requirements, not just a
  design change, so it is deferred rather than decided here.
- Should `architecture-review` read the relevant `openspec/specs/<capability>/spec.md` when a
  pull request maps to a known change, to check the implementation against what was specified?
  Left out of this change's scope; adding it later would extend the
  `architecture-review-checklist` skill without requiring new requirements or a new decision
  here.
