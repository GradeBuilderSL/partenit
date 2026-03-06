"""
partenit-eval — Robot Evaluation Platform.

Measures the safety and behavioral quality of robot controllers
by running scenarios and computing grades (A–F).

Usage:
    from partenit.safety_bench.eval import EvalRunner, ControllerConfig

    runner = EvalRunner()
    report = runner.run_scenario(
        "scenarios/human_crossing.yaml",
        controllers=[
            ControllerConfig("baseline", policy_paths=[]),
            ControllerConfig("guarded", policy_paths=["policies/warehouse.yaml"]),
        ],
    )
    print(report.summary_table())
"""

from partenit.safety_bench.eval.metrics import EvalMetrics, compute_metrics
from partenit.safety_bench.eval.runner import ControllerConfig, EvalReport, EvalRunner

__all__ = [
    "EvalRunner",
    "ControllerConfig",
    "EvalReport",
    "EvalMetrics",
    "compute_metrics",
]
