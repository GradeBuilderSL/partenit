"""
BenchmarkRunner — wraps ScenarioRunner with seed management and comparison support.

This is the Level 1 engine: pure Python, deterministic, CPU-only.
Level 2 (Isaac Sim / ROS2 backends) will use the same interface.
"""

from __future__ import annotations

from pathlib import Path

from partenit.safety_bench.scenario import ScenarioResult, ScenarioRunner


class BenchmarkRunner:
    """
    Runs benchmarks with controlled seeds and optional guard comparison.

    Usage:
        runner = BenchmarkRunner()
        results = runner.run_comparison("./human_crossing_path.yaml", seed=42)
        # results is a list of ScenarioResult (with_guard + without_guard)
    """

    def __init__(self) -> None:
        self._runner = ScenarioRunner()

    def run(
        self,
        path: str | Path,
        seed: int = 42,
        with_guard: bool = True,
    ) -> ScenarioResult:
        """Run a single scenario with the given seed."""
        config = self._runner.load(path)
        return self._runner.run(config, with_guard=with_guard, seed=seed)

    def run_comparison(
        self,
        path: str | Path,
        seed: int = 42,
    ) -> list[ScenarioResult]:
        """
        Run the same scenario with AND without guard.

        Both runs use the same seed so the world physics are identical —
        the only variable is whether the guard intervenes.

        Returns:
            [result_with_guard, result_without_guard]
        """
        config = self._runner.load(path)
        with_guard = self._runner.run(config, with_guard=True, seed=seed)
        without_guard = self._runner.run(config, with_guard=False, seed=seed)
        return [with_guard, without_guard]

    def run_all(
        self,
        directory: str | Path,
        seed: int = 42,
        compare: bool = True,
    ) -> list[ScenarioResult]:
        """
        Run all scenario YAML files in a directory.

        Args:
            directory: Path containing *.yaml scenario files.
            seed:      Reproducibility seed applied to all scenarios.
            compare:   If True, run each scenario with AND without guard.

        Returns:
            Flat list of ScenarioResult objects.
        """
        directory = Path(directory)
        files = sorted(
            list(directory.glob("**/*.yaml")) + list(directory.glob("**/*.yml"))
        )
        results: list[ScenarioResult] = []
        for path in files:
            try:
                if compare:
                    results.extend(self.run_comparison(path, seed=seed))
                else:
                    results.append(self.run(path, seed=seed, with_guard=True))
            except Exception as exc:
                import warnings
                warnings.warn(f"Skipped {path.name}: {exc}")
        return results
