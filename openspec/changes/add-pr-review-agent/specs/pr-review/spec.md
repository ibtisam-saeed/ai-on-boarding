## Purpose

Gives every pull request automated, deterministic lint feedback, and gives repository
collaborators an on-demand, multi-angle AI-assisted review, both surfaced as individually
isolated comments on the pull request itself.

## ADDED Requirements

### Requirement: Run deterministic lint checks on every pull request
The system SHALL run a deterministic lint check on every pull request without requiring any
model invocation or human request.

#### Scenario: Pull request opened or updated
- **WHEN** a pull request is opened or its branch receives a new commit
- **THEN** the lint check runs and reports a pass or fail status on the pull request

### Requirement: Post lint violations as inline comments
The system SHALL post each non-autofixable lint violation located on a line the pull request
changed as its own inline review comment attached to that file and line. Autofixable violations
SHALL NOT be posted as comments.

#### Scenario: Non-autofixable violation on a changed line
- **WHEN** the lint check finds a violation with no safe automatic fix, on a line added or
  modified by the pull request
- **THEN** an inline comment describing that violation appears on that file and line

#### Scenario: Autofixable violation
- **WHEN** the lint check finds a violation that has a safe automatic fix
- **THEN** no inline comment is posted for that violation

### Requirement: Trigger an AI-assisted review only from a collaborator's request
The system SHALL start an AI-assisted review only when a repository collaborator posts a comment
containing the trigger phrase on a pull request. A comment from a non-collaborator SHALL NOT
start a review.

#### Scenario: Collaborator requests a review
- **WHEN** a repository collaborator comments on a pull request using the trigger phrase
- **THEN** an AI-assisted review starts for that pull request

#### Scenario: Non-collaborator comments the trigger phrase
- **WHEN** a user who is not a repository collaborator comments using the trigger phrase
- **THEN** no AI-assisted review starts

### Requirement: Select only relevant review skills
The system SHALL determine, from the requester's comment and the files the pull request changed,
which review skills apply, and SHALL run only those skills. It SHALL NOT run every available
skill on every request by default.

#### Scenario: Request names a specific concern
- **WHEN** a collaborator's trigger comment names a specific concern (for example, security)
- **THEN** only the skill(s) matching that concern run

#### Scenario: Request names no specific concern
- **WHEN** a collaborator's trigger comment requests a review without naming a concern
- **THEN** the system selects skills based on the files the pull request changed rather than
  running every skill unconditionally

### Requirement: Run selected skills concurrently
When more than one skill is selected for a review, the system SHALL run them concurrently rather
than one after another.

#### Scenario: Multiple skills selected
- **WHEN** an AI-assisted review selects more than one skill
- **THEN** those skills' reviews run at the same time rather than being executed in sequence

### Requirement: Post each finding as its own isolated comment
The system SHALL post each finding, from any source, as its own review comment. A finding SHALL
NOT be merged with another finding's text, regardless of whether they come from the same or
different skills.

#### Scenario: Findings from different skills
- **WHEN** two different skills each produce a finding for the same pull request
- **THEN** each finding is posted as its own separate comment

#### Scenario: Finding attaches to a changed line
- **WHEN** a finding's file and line are part of the pull request's diff
- **THEN** the finding is posted as an inline comment attached to that file and line

### Requirement: Fall back to a general comment for unattachable findings
The system SHALL post a finding whose file or line cannot be attached to a position in the
pull request's diff as its own general pull request comment instead of discarding it or
attaching it to an unrelated line.

#### Scenario: Finding has no valid diff position
- **WHEN** a finding's file is not part of the diff, or its line is not part of any changed
  hunk
- **THEN** the finding is posted as a general pull request comment rather than an inline comment,
  and is still posted as its own comment

### Requirement: Post one summary per AI-assisted review run
The system SHALL post exactly one summary comment or review per AI-assisted review run, stating
which skills ran and how many findings were posted. The summary SHALL NOT repeat the content of
any individual finding.

#### Scenario: Review run completes
- **WHEN** an AI-assisted review run finishes selecting skills, collecting findings, and posting
  comments
- **THEN** exactly one summary is posted naming the skills that ran and the number of findings
  posted, with no finding text repeated in it

### Requirement: Suppress duplicate findings
The system SHALL post at most one comment for a given underlying issue, even when that issue is
identified by more than one source (the lint check and a skill, two different skills, or a
repeated review run after new commits).

#### Scenario: Same issue found by two sources
- **WHEN** the lint check and a review skill, or two review skills, each identify the same
  underlying issue at the same location
- **THEN** only one comment for that issue is posted

#### Scenario: Repeated review run
- **WHEN** a collaborator triggers a second AI-assisted review, or the lint check runs again,
  after previous findings were already posted and remain unresolved
- **THEN** previously posted findings are not posted again; only genuinely new findings result in
  new comments

### Requirement: Treat reviewed content as data, not instructions
The system SHALL treat the pull request's diff, file contents, and comment text as content under
review, and SHALL NOT follow instructions contained within that content.

#### Scenario: Diff contains an embedded instruction
- **WHEN** a pull request's diff, a file it changes, or a comment on it contains text phrased as
  an instruction (for example, telling the reviewer to report no findings or to ignore its
  configured behaviour)
- **THEN** the review proceeds according to its configured behaviour and that embedded text is
  evaluated only as content, not followed as an instruction

### Requirement: Never disclose secret values in a finding
The system SHALL describe a finding that concerns an exposed secret or credential by its
location and nature only, and SHALL NOT include the secret's literal value in any comment it
posts.

#### Scenario: Finding concerns an exposed credential
- **WHEN** a finding identifies a hardcoded secret or credential
- **THEN** the posted comment names the location and issue without reproducing the secret's
  actual value

### Requirement: Findings are advisory and do not block merge
The system SHALL NOT cause a pull request to be blocked from merging on the basis of any finding
it posts, regardless of severity, beyond the lint check's own pass/fail status.

#### Scenario: A finding of the highest severity is posted
- **WHEN** a finding with the highest defined severity is posted on a pull request
- **THEN** the pull request's mergeability is unaffected by that finding
