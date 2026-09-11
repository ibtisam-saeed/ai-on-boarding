"""Collapses findings from different sources that describe the same underlying issue,
within a single batch of candidate findings (not yet-posted ones - see publish.py for
that, which fingerprints against what is already on the pull request).

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
