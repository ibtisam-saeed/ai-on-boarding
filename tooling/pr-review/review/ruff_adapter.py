"""Converts `ruff check --output-format json` output into the shared Finding
schema, skipping anything Ruff can safely fix on its own - a safely-autofixable
violation doesn't need a human's attention as a standalone comment; it needs
`ruff check --fix` run, which the failing CI check already communicates.

Run as: python -m review.ruff_adapter --input <ruff.json> --repo-root <path> --out <findings.json>

See openspec/changes/add-pr-review-agent/design.md - Decision 4 (the publishing
pipeline is source-agnostic) and the spec's "Post lint violations as inline
comments" requirement.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from review.schema import Finding

CATEGORY = "code-quality"
SEVERITY = "minor"  # Ruff does not grade violations on our blocker/major/minor/info scale.
SOURCE = "ruff"


def _is_safely_autofixable(violation: dict) -> bool:
    fix = violation.get("fix")
    return bool(fix) and fix.get("applicability") == "safe"


def convert(violations: list[dict], repo_root: str) -> list[Finding]:
    findings: list[Finding] = []
    for violation in violations:
        if _is_safely_autofixable(violation):
            continue

        explanation = violation["message"]
        if violation.get("url"):
            explanation += f"\n\nSee {violation['url']} for details."

        findings.append(
            Finding(
                category=CATEGORY,
                severity=SEVERITY,
                file=os.path.relpath(violation["filename"], repo_root),
                line=violation["location"]["row"],
                title=f"{violation['code']}: {violation['message']}",
                explanation=explanation,
                suggested_fix="",
                source=SOURCE,
            )
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="ruff check --output-format json output")
    parser.add_argument("--repo-root", type=Path, required=True, help="Repo root, to make file paths relative")
    parser.add_argument("--out", type=Path, required=True, help="Where to write the Finding JSON array")
    args = parser.parse_args(argv)

    violations = json.loads(args.input.read_text())
    findings = convert(violations, str(args.repo_root))
    args.out.write_text(json.dumps([f.model_dump() for f in findings], indent=2) + "\n")

    print(
        f"Converted {len(violations)} Ruff violation(s) into {len(findings)} finding(s) "
        f"({len(violations) - len(findings)} safely auto-fixable, skipped)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
