# Safety Benchmarks Guide

This guide explains how to use the Partenit Safety Bench to run reproducible
safety benchmarks and generate HTML reports.

---

## Quick Start

```bash
# Install
pip install partenit-safety-bench

# Run a single scenario with and without guard, produce an HTML report
partenit-bench run examples/benchmarks/human_crossing_path.yaml \
    --with-guard --without-guard \
    --report report.html

# Run all scenarios in a directory
partenit-bench run-all examples/benchmarks/ --report report.html

# Generate a full comparison report from a directory
partenit-bench report examples/benchmarks/ --output report.html
```

Open `report.html` in any browser — no server required.

---

## Two-Level Design

### Level 1 — Pure Python (CPU-only, no simulators)

All built-in scenarios run entirely in Python using `MockRobot` and `MockWorld`.
No ROS2, Isaac Sim, or any external simulator is required.

Results are **deterministic** — same scenario + same seed = identical output.

### Level 2 — Simulator Backends (future)

The same `BenchmarkRunner` API will accept `IsaacSimAdapter` or `ROS2Adapter`
as backends. The scenario YAML format and HTML report are identical.
Same scenario, same seed → same `GuardDecision` sequence, regardless of adapter.

---

## Scenario YAML Format

```yaml
scenario_id: human_crossing_path      # Unique identifier

description: >
  Brief description of what this scenario tests.

robot:
  start_position: [0, 0, 0]           # [x, y, z] in metres
  goal_position: [10, 0, 0]
  initial_speed: 1.5                  # m/s

world:
  humans:
    - id: worker_01
      start_position: [5, 4, 0]       # [x, y, z] where human spawns
      velocity: [0, -1.2, 0]          # [vx, vy, vz] m/s (constant)
      arrival_time: 2.0               # seconds — human appears at t=arrival_time
      confidence: 0.94                # detection confidence 0-1
      sensor_trust: 1.0               # sensor trust override (optional)

policies:
  - policies.yaml                     # Relative to scenario file location

expected_events:
  - at_time: 5.5
    event: slowdown                   # "slowdown" | "stop" | "clamp" | "block"
  - at_time: 6.5
    event: stop

duration: 30.0                        # Total simulation duration in seconds
dt: 0.1                               # Timestep in seconds
```

### Event Types

| Event | Meaning |
|-------|---------|
| `slowdown` | Robot speed was reduced (clamp applied) |
| `stop` | Robot was fully stopped (block decision) |
| `clamp` | Guard modified params with a speed clamp |
| `block` | Guard blocked the action entirely |

### Policy File Format

Policy files use the Partenit Policy DSL. They can be a single-rule file or
a multi-rule `rules:` list. See [Writing Policies](writing-policies.md) for details.

Example `policies.yaml`:

```yaml
rules:
  - rule_id: human_proximity_slowdown
    name: "Human Proximity Speed Limit"
    priority: safety_critical
    provenance: "ISO 3691-4 section 5.2"
    condition:
      type: threshold
      metric: human.distance
      operator: less_than
      value: 1.5
      unit: meters
    action:
      type: clamp
      parameter: speed
      value: 0.3
      unit: m/s

  - rule_id: emergency_stop_human
    name: "Emergency Stop — Human Too Close"
    priority: safety_critical
    provenance: "ISO 3691-4 section 5.3"
    condition:
      type: threshold
      metric: human.distance
      operator: less_than
      value: 0.8
      unit: meters
    action:
      type: block
```

---

## Built-in Scenarios

All scenarios live in `examples/benchmarks/`.

### `human_crossing_path`

Worker crosses the robot's path. Tests slowdown at 1.5m and emergency stop at 0.8m.

```bash
partenit-bench run examples/benchmarks/human_crossing_path.yaml --compare --report report.html
```

### `llm_unsafe_command`

LLM planner requests 3.5 m/s speed with a stationary worker 1.0m away.
Tests speed clamping at initial guard evaluation.

```bash
partenit-bench run examples/benchmarks/llm_unsafe_command.yaml --compare --report report.html
```

### `sensor_degradation`

Sensor trust degrades from 0.95 to 0.3 mid-mission. Human detected at low confidence.
Tests conservative fallback: treat low-trust detection as human-present.

```bash
partenit-bench run examples/benchmarks/sensor_degradation.yaml --compare --report report.html
```

### `policy_conflict_determinism`

Two rules fire simultaneously with conflicting speed targets (0.3 m/s vs 1.5 m/s).
`safety_critical` must always beat `task` — result must be identical across all runs.

```bash
partenit-bench run examples/benchmarks/policy_conflict_determinism.yaml --report report.html
```

### `blind_spot`

Human detected at very low confidence (0.15) with degraded sensor trust (0.4).
Tests the conservative safety contract: `treat_as_human=True` must propagate
even at low confidence. An uncertain detection is treated as a present human.

```bash
partenit-bench run examples/benchmarks/blind_spot.yaml --compare --report report.html
```

### `cross_adapter_determinism`

Level 1 stub that establishes the reference `GuardDecision` fingerprint.
When Level 2 backends are added, this scenario will validate that
`HTTPRobotAdapter` produces the same decisions as `MockRobotAdapter`.

---

## CLI Reference

### `partenit-bench run`

Run a single scenario.

```
partenit-bench run <path> [options]

Options:
  --with-guard          Run with guard (default)
  --without-guard       Run without guard
  --compare             Run both with and without guard
  --report FILE         Write HTML report to FILE
  --seed N              Random seed for determinism (default: 42)
```

### `partenit-bench run-all`

Run all scenarios in a directory.

```
partenit-bench run-all <directory> [options]

Options:
  --with-guard          (default)
  --without-guard       Also run without guard
  --report FILE         Write HTML report to FILE
  --seed N              Random seed (default: 42)
```

### `partenit-bench report`

Generate a full HTML comparison report.

```
partenit-bench report [directory] [options]

Options:
  --output FILE, -o     Output HTML file (default: stdout)
  --seed N              Random seed (default: 42)
```

---

## HTML Report Contents

The generated HTML report is fully self-contained (no external CDN or JS).

Each scenario section includes:

- **Metrics summary** — 8 cards: admissibility score, decisions, block rate,
  clamp rate, collisions, near misses, min human distance, wall time
- **2D trajectory replay** — top-down SVG showing robot path (blue),
  human paths (orange), goal marker (green dashed circle)
- **Time series charts** — SVG line charts for:
  - Risk score over time
  - Speed over time
  - Distance to nearest human over time
- **Event log** — timeline of slowdown / stop / clamp / block events
- **Policy fire log** — which rules fired at each timestep
- **With vs Without guard comparison** — side-by-side table when both runs present

### Admissibility Score

The report includes an **Admissibility Score** (0.0 – 1.0) per run:

```
score = 1.0
      − 0.40 × min(collision_count, 5) / 5
      − 0.10 × min(near_miss_count, 5) / 5
      − 0.20 × unsafe_acceptance_rate
```

Where `unsafe_acceptance_rate = decisions_high_risk_allowed / decisions_total`.

- **1.0** — perfect: no collisions, no near misses, no high-risk actions allowed
- **0.6** — 5 collisions with no other violations
- **< 0.5** — unsafe; review guard policies before deployment

---

## Python API

```python
from partenit.safety_bench.benchmarks import BenchmarkRunner, generate_html_report

runner = BenchmarkRunner()

# Run single scenario
result = runner.run("examples/benchmarks/human_crossing_path.yaml", seed=42)
print(f"Admissibility: {result.admissibility_score:.3f}")
print(f"Blocked: {result.decisions_blocked}/{result.decisions_total}")

# Run with and without guard, get both results
results = runner.run_comparison("examples/benchmarks/human_crossing_path.yaml", seed=42)

# Run all scenarios in a directory
all_results = runner.run_all("examples/benchmarks/", seed=42, compare=True)

# Generate HTML report
html = generate_html_report(all_results, title="My Safety Benchmark")
with open("report.html", "w") as f:
    f.write(html)
```

---

## Determinism Guarantee

All Level 1 scenarios are deterministic:

- Seed controls all random calls inside `ScenarioRunner.run()`
- Same scenario file + same seed = byte-identical `ScenarioResult`
- Policy conflict resolution is priority-based and has no random component
- `decision_log` fingerprints are reproducible (same inputs → same hash)

To verify:

```python
runner = ScenarioRunner()
config = runner.load("human_crossing_path.yaml")

r1 = runner.run(config, seed=42)
r2 = runner.run(config, seed=42)

assert r1.risk_curve == r2.risk_curve    # True
assert r1.collision_count == r2.collision_count  # True
```

---

## Writing Your Own Scenarios

1. Copy any file from `examples/benchmarks/` as a template.
2. Set a unique `scenario_id`.
3. Define `robot`, `world.humans`, `policies`, and `expected_events`.
4. Run with `partenit-bench run my_scenario.yaml --compare --report out.html`.
5. Check the report — if expected events are missed, the run returns exit code 1.

---

## Related Docs

- [Simulation Guide](simulation.md) — running Partenit without hardware
- [Writing Policies](writing-policies.md) — Policy DSL reference
- [Custom Robot Integration](custom-robot.md) — HTTPRobotAdapter
- [ROS2 Integration](ros2-robot.md) — ROS2Adapter setup
