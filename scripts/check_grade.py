#!/usr/bin/env python3
"""
Partenit GitHub Action — safety grade check.

Runs a scenario with the guarded controller and fails if the safety grade
is below the required minimum.

Environment variables (set by action.yml):
    PARTENIT_SCENARIO   Path to scenario YAML
    PARTENIT_POLICY     Path to policy file or directory
    PARTENIT_MIN_GRADE  Minimum acceptable grade: A, B, C, or D
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

GRADE_ORDER = ["A", "B", "C", "D", "F"]


def _write_output(key: str, value: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"{key}={value}\n")


def main() -> int:
    scenario = os.environ.get("PARTENIT_SCENARIO", "").strip()
    policy_path = os.environ.get("PARTENIT_POLICY", "").strip()
    min_grade = os.environ.get("PARTENIT_MIN_GRADE", "").strip().upper()

    if not scenario:
        print("::error::PARTENIT_SCENARIO is not set", flush=True)
        return 1

    if min_grade not in GRADE_ORDER:
        print(
            f"::error::Invalid min-grade '{min_grade}'. "
            f"Valid values: A, B, C, D",
            flush=True,
        )
        return 1

    # Import here so errors are reported cleanly
    try:
        from partenit.safety_bench.eval import EvalRunner, ControllerConfig
    except ImportError as exc:
        print(f"::error::Cannot import partenit-safety-bench: {exc}", flush=True)
        return 1

    policy_paths = [policy_path] if policy_path and Path(policy_path).exists() else []

    runner = EvalRunner()
    try:
        report = runner.run_scenario(
            scenario,
            controllers=[
                ControllerConfig("guarded", policy_paths=policy_paths),
            ],
        )
    except Exception as exc:
        print(f"::error::Scenario run failed: {exc}", flush=True)
        return 1

    if not report.metrics:
        print("::error::No evaluation metrics returned", flush=True)
        return 1

    m = report.metrics[0]
    grade: str = m.grade
    score: float = m.overall_score

    print(f"Safety grade : {grade}", flush=True)
    print(f"Overall score: {score:.3f}", flush=True)
    print(f"Safety score : {m.safety_score:.3f}", flush=True)
    print(f"Efficiency   : {m.efficiency_score:.3f}", flush=True)
    print(f"AI quality   : {m.ai_score:.3f}", flush=True)

    _write_output("safety_grade", grade)
    _write_output("overall_score", f"{score:.4f}")

    if GRADE_ORDER.index(grade) > GRADE_ORDER.index(min_grade):
        print(
            f"::error::Safety grade {grade} is below minimum required {min_grade}. "
            f"Score: {score:.3f}. Improve policies or lower the threshold.",
            flush=True,
        )
        return 1

    print(
        f"::notice::Safety grade {grade} meets requirement (min: {min_grade})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
