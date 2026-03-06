"""
partenit-eval Demo — Robot Safety Evaluation.

Compares two controllers on the same scenario and prints a safety grade.

This is the "robot evaluation platform" use case:
  Developer has their own robot controller logic.
  They want to measure: is my controller safe? How does version A compare to B?

Run:
    python examples/eval_demo.py

Or via CLI:
    partenit-eval run examples/benchmarks/human_crossing_path.yaml --report eval.html
"""

from pathlib import Path

from partenit.safety_bench.eval import ControllerConfig, EvalRunner
from partenit.safety_bench.eval.report_eval import generate_eval_html

SCENARIO = Path(__file__).parent / "benchmarks" / "human_crossing_path.yaml"
POLICIES = Path(__file__).parent / "warehouse" / "policies.yaml"
REPORT_PATH = Path("eval_report.html")

print("=== Partenit Robot Evaluation Platform ===\n")
print(f"Scenario: {SCENARIO.name}")
print("Controllers: baseline (no guard)  vs  guarded (with policies)\n")

# ── Define controllers ────────────────────────────────────────────────────────
controllers = [
    ControllerConfig(
        name="baseline",
        policy_paths=[],  # no safety guard
        description="Raw controller, no safety checks",
    ),
    ControllerConfig(
        name="guarded",
        policy_paths=[str(POLICIES)],
        description="Controller with Partenit safety guard",
    ),
]

# ── Run evaluation ─────────────────────────────────────────────────────────────
runner = EvalRunner()
report = runner.run_scenario(SCENARIO, controllers=controllers, seed=42)

# ── Print results ──────────────────────────────────────────────────────────────
print(report.summary_table())

for m in report.metrics:
    print(f"\n{m.controller_name}:")
    print(f"  Grade:          {m.grade}")
    print(f"  Safety score:   {m.safety_score:.2f}")
    print(f"  Efficiency:     {m.efficiency_score:.2f}")
    print(f"  AI quality:     {m.ai_score:.2f}")
    print(f"  Overall:        {m.overall_score:.2f}")
    print(f"  Collisions:     {m.collision_count}")
    print(f"  Near misses:    {m.near_miss_count}")
    print(f"  Min distance:   {m.min_human_distance_m:.2f} m")
    print(f"  Goal reached:   {m.task_completion_rate >= 1.0}")

# ── HTML report ────────────────────────────────────────────────────────────────
html = generate_eval_html(report, title="Demo Evaluation Report")
REPORT_PATH.write_text(html, encoding="utf-8")
print(f"\nHTML report: {REPORT_PATH}")
print("Open in any browser — no server required.")
