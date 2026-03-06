"""
EvalRunner — Robot Evaluation Platform runner.

Runs scenarios with multiple controller configurations and produces
an EvalReport with grades and comparison tables.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from partenit.safety_bench.eval.metrics import EvalMetrics, compute_metrics
from partenit.safety_bench.scenario import ScenarioRunner


@dataclass
class ControllerConfig:
    """
    Defines a "controller" variant to evaluate.

    In Partenit terms, a controller is defined by its policy set:
    no policies = unsafe baseline, with policies = guarded controller.

    Args:
        name:          Display name in reports (e.g. "baseline", "guarded_v2").
        policy_paths:  List of policy files or directories to load.
                       Empty list = no guard (unsafe baseline).
        risk_threshold: Risk score threshold above which actions are blocked.
        description:   Optional description shown in the report.
    """

    name: str
    policy_paths: list[str] = field(default_factory=list)
    risk_threshold: float = 0.8
    description: str = ""


@dataclass
class EvalReport:
    """
    Evaluation results for one or more scenarios and controllers.

    Contains:
        metrics: List of EvalMetrics, one per (scenario, controller) pair.
        scenarios: List of scenario IDs evaluated.
        controllers: List of controller names.
        raw_results: Raw ScenarioResult objects keyed by (scenario_id, controller_name).
                     Used by the HTML report to render trajectory and time-series charts.
    """

    metrics: list[EvalMetrics] = field(default_factory=list)
    scenarios: list[str] = field(default_factory=list)
    controllers: list[str] = field(default_factory=list)
    raw_results: dict[tuple[str, str], Any] = field(default_factory=dict)

    def get(self, scenario_id: str, controller_name: str) -> EvalMetrics | None:
        """Look up metrics for a specific (scenario, controller) pair."""
        for m in self.metrics:
            if m.scenario_id == scenario_id and m.controller_name == controller_name:
                return m
        return None

    def summary_table(self) -> str:
        """Return a plain-text summary table."""
        lines = [
            f"{'Controller':<22} {'Scenario':<28} {'Grade':>5} {'Safety':>8} {'Efficiency':>11} {'AI':>6} {'Overall':>8}",
            "─" * 90,
        ]
        for m in self.metrics:
            lines.append(
                f"{m.controller_name:<22} {m.scenario_id:<28} "
                f"{m.grade:>5} {m.safety_score:>8.2f} {m.efficiency_score:>11.2f} "
                f"{m.ai_score:>6.2f} {m.overall_score:>8.2f}"
            )
        return "\n".join(lines)

    def best_controller(self, scenario_id: str) -> EvalMetrics | None:
        """Return the controller with the highest overall_score for a scenario."""
        candidates = [m for m in self.metrics if m.scenario_id == scenario_id]
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.overall_score)


class EvalRunner:
    """
    Runs scenarios with multiple controller configurations and evaluates them.

    Internally uses ScenarioRunner for each (scenario, controller) pair.
    Same seed is used for all runs to ensure fair physics comparison.

    Usage:
        runner = EvalRunner()
        report = runner.run_scenario(
            "scenarios/human_crossing.yaml",
            controllers=[
                ControllerConfig("baseline", []),
                ControllerConfig("guarded", ["policies/warehouse.yaml"]),
            ],
        )
        print(report.summary_table())
    """

    def __init__(self) -> None:
        self._runner = ScenarioRunner()

    def run_scenario(
        self,
        scenario_path: str | Path,
        controllers: list[ControllerConfig],
        seed: int = 42,
    ) -> EvalReport:
        """
        Evaluate multiple controllers on a single scenario.

        Args:
            scenario_path: Path to scenario YAML file.
            controllers:   List of ControllerConfig variants to compare.
            seed:          Random seed (same for all controllers = fair comparison).

        Returns:
            EvalReport with EvalMetrics for each controller.
        """
        scenario_path = Path(scenario_path)
        config = self._runner.load(scenario_path)
        report = EvalReport(
            scenarios=[config.scenario_id],
            controllers=[c.name for c in controllers],
        )

        for ctrl in controllers:
            with_guard = bool(ctrl.policy_paths)
            # Temporarily override policy_paths if controller specifies them
            original_paths = config.policy_paths
            if ctrl.policy_paths:
                config.policy_paths = ctrl.policy_paths
            elif not ctrl.policy_paths:
                # Baseline: run without guard
                config.policy_paths = []

            try:
                result = self._runner.run(
                    config,
                    with_guard=with_guard,
                    seed=seed,
                )
                metrics = compute_metrics(ctrl.name, result)
                report.metrics.append(metrics)
                report.raw_results[(config.scenario_id, ctrl.name)] = result
            except Exception as exc:
                warnings.warn(f"EvalRunner: failed to run controller '{ctrl.name}': {exc}")
            finally:
                config.policy_paths = original_paths

        return report

    def run_suite(
        self,
        scenario_dir: str | Path,
        controllers: list[ControllerConfig],
        seed: int = 42,
    ) -> EvalReport:
        """
        Evaluate multiple controllers across all scenarios in a directory.

        Args:
            scenario_dir: Directory containing *.yaml scenario files.
            controllers:  List of controller variants to compare.
            seed:         Reproducibility seed.

        Returns:
            EvalReport aggregating results from all scenarios.
        """
        scenario_dir = Path(scenario_dir)
        files = sorted(
            list(scenario_dir.glob("**/*.yaml")) + list(scenario_dir.glob("**/*.yml"))
        )

        combined = EvalReport(controllers=[c.name for c in controllers])

        for path in files:
            try:
                sub_report = self.run_scenario(path, controllers, seed=seed)
                combined.metrics.extend(sub_report.metrics)
                combined.scenarios.extend(sub_report.scenarios)
            except Exception as exc:
                warnings.warn(f"EvalRunner: skipped {path.name}: {exc}")

        return combined
