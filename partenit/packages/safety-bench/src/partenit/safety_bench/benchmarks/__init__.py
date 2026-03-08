"""
Partenit benchmark suite — deterministic, simulation-first.

Level 1: pure Python, CPU-only, no external simulators required.
Level 2: same interface, optional Isaac Sim / ROS2 backends (added later).

Usage:
    from partenit.safety_bench.benchmarks import BenchmarkRunner, generate_html_report

    runner = BenchmarkRunner()
    results = runner.run_comparison("./scenarios/human_crossing_path.yaml", seed=42)
    html = generate_html_report(results)
    Path("report.html").write_text(html)
"""

from partenit.safety_bench.benchmarks.report_html import generate_html_report
from partenit.safety_bench.benchmarks.runner import BenchmarkRunner

__all__ = ["BenchmarkRunner", "generate_html_report"]
