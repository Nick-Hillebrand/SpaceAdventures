#!/usr/bin/env python3
"""Per-module branch coverage gate (CLAUDE.md non-negotiable rule 1).

Every `app/**/*.py` file with at least one branch must have >= 80% branch
coverage. Files with zero branches (e.g. `__init__.py`, pure data modules)
pass automatically — they have nothing to gate on.

Usage:
    pytest --cov=app --cov-branch --cov-report=json
    python scripts/check_module_coverage.py [path/to/coverage.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

THRESHOLD = 80.0


def check(coverage_path: Path) -> int:
    try:
        data = json.loads(coverage_path.read_text())
    except FileNotFoundError:
        print(
            f"error: {coverage_path} not found — run "
            "`pytest --cov=app --cov-branch --cov-report=json` first",
            file=sys.stderr,
        )
        return 2

    failures: list[tuple[str, float, int]] = []
    checked = 0

    for filename, file_data in sorted(data["files"].items()):
        if not filename.startswith("app/") or not filename.endswith(".py"):
            continue
        summary = file_data["summary"]
        num_branches = summary.get("num_branches", 0)
        if num_branches < 1:
            continue
        checked += 1
        percent = summary.get("percent_branches_covered", 0.0)
        if percent < THRESHOLD:
            failures.append((filename, percent, num_branches))

    if failures:
        print(f"Per-module branch coverage gate FAILED ({len(failures)} of {checked} modules below {THRESHOLD:.0f}%):\n")
        for filename, percent, num_branches in failures:
            print(f"  {filename}: {percent:.1f}% branch coverage ({num_branches} branches)")
        return 1

    print(f"Per-module branch coverage gate passed ({checked} modules with branches, all >= {THRESHOLD:.0f}%).")
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("coverage.json")
    sys.exit(check(path))
