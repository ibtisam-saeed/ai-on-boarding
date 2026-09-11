"""Collapses findings that describe the same underlying issue - both within a single
batch of new candidates (`collapse_duplicates`) and against what a pull request
already carries (`find_match`, used by publish.py's already-posted check). The same
location+title-similarity heuristic serves both: a second, independent LLM call
reviewing unchanged code will not reproduce a finding's title byte-for-byte, so
publish.py cannot rely on exact identity alone once findings come from a model
rather than a deterministic tool like Ruff - see openspec/changes/
add-pr-review-agent/traceability.md for the real run that proved this.

See openspec/changes/add-pr-review-agent/design.md - Decision 5 and the "Risks" entry
on this heuristic needing validation against real examples before it is trusted.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from review.schema import SEVERITY_RANK, Finding

LINE_WINDOW = 3
TITLE_SIMILARITY_THRESHOLD = 0.6


def _title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def _same_location(a: Finding, b: Finding) -> bool:
    if a.file != b.file:
        return False
    if a.line is None or b.line is None:
        return a.line == b.line
    return abs(a.line - b.line) <= LINE_WINDOW


def find_match(candidate: Finding, pool: list[Finding]) -> Finding | None:
    """The first finding in `pool` that appears to describe the same underlying
    issue as `candidate` (same location, similar title), or None. Used against
    already-posted findings reconstructed from a pull request's existing comments -
    unlike `collapse_duplicates`, there is no "survivor" to pick here, since an
    already-posted finding always wins: the candidate is simply not reposted.
    """
    for other in pool:
        if _same_location(candidate, other) and (
            _title_similarity(candidate.title, other.title) >= TITLE_SIMILARITY_THRESHOLD
        ):
            return other
    return None


def _pick_survivor(a: Finding, b: Finding) -> tuple[Finding, Finding]:
    """Returns (survivor, dropped), keeping the higher-severity finding."""
    if SEVERITY_RANK[b.severity] > SEVERITY_RANK[a.severity]:
        return b, a
    return a, b


def _note_also_flagged(finding: Finding, other_sources: list[str]) -> Finding:
    if not other_sources:
        return finding
    sources = ", ".join(sorted(set(other_sources)))
    return finding.model_copy(
        update={"explanation": f"{finding.explanation}\n\n(Also flagged by: {sources}.)"}
    )


def collapse_duplicates(findings: list[Finding]) -> list[Finding]:
    """Merges findings at the same location whose titles are near-identical, keeping
    the higher-severity one and noting which other sources agreed. Findings at the
    same location with genuinely different titles are left as separate findings -
    that is multiple sources raising distinct concerns, not a duplicate.
    """
    survivors: list[Finding] = []
    merged_sources: list[list[str]] = []

    for finding in findings:
        matched_index = None
        for index, survivor in enumerate(survivors):
            if _same_location(finding, survivor) and (
                _title_similarity(finding.title, survivor.title) >= TITLE_SIMILARITY_THRESHOLD
            ):
                matched_index = index
                break

        if matched_index is None:
            survivors.append(finding)
            merged_sources.append([])
            continue

        current, dropped = survivors[matched_index], finding
        winner, loser = _pick_survivor(current, dropped)
        merged_sources[matched_index].append(loser.source)
        survivors[matched_index] = winner

    return [
        _note_also_flagged(survivor, sources)
        for survivor, sources in zip(survivors, merged_sources)
    ]
