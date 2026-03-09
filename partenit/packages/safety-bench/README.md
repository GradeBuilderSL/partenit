[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# partenit-safety-bench

> **Test your robot's safety behaviour before deploying to hardware.**

`partenit-safety-bench` runs deterministic safety scenarios in pure Python —
no simulator, no hardware required. It compares "without guard" vs "with guard"
and produces an HTML report with metrics, timeline, and a 2D replay.

```bash
pip install partenit-safety-bench
```

---

## Quickstart

```bash
# Run a built-in scenario and open the HTML report
partenit-bench run examples/benchmarks/human_crossing_path.yaml \
    --with-guard --without-guard \
    --report report.html

# Run all scenarios in a directory
partenit-bench run-all examples/benchmarks/ --report suite.html
```

---

## Built-in scenarios

| Scenario | Description |
|---|---|
| `human_crossing_path` | Worker crosses robot trajectory at 2 m — guard must slow down and stop |
| `llm_unsafe_command` | LLM requests speed=3.0 near a human — guard must clamp or block |
| `sensor_degradation` | LiDAR trust drops mid-mission — guard must activate fallback |
| `policy_conflict_determinism` | Two rules fire simultaneously — resolution must be deterministic |
| `blind_spot` | Human in low-confidence detection zone — guard must treat as human |

All scenarios are YAML files in [examples/benchmarks/](../../../examples/benchmarks/).

---

## Scenario format

```yaml
scenario_id: human_crossing_path
duration: 6.0       # seconds
dt: 0.1             # simulation tick

robot:
  start_position: [0, 0, 0]
  goal_position: [10, 0, 0]
  initial_speed: 1.5

world:
  humans:
    - id: human_01
      start_position: [5, 3, 0]
      arrival_time: 2.0        # enters robot path at t=2.0s
  sensor_trust_profile:        # optional: degrade trust over time
    - at_time: 3.0
      trust: 0.4

policies: ["examples/warehouse/policies.yaml"]

expected_events:
  - at_time: 2.5
    event: slowdown            # guard must fire human_proximity_slowdown
  - at_time: 3.0
    event: stop                # guard must fire emergency_stop
```

---

## HTML report

The report includes:

- **2D replay** — top-down view with robot path, human positions, danger zones, slowdown/stop markers
- **Time series charts** — risk score, speed, human distance, sensor trust over time
- **Event log** — every policy that fired, with timestamps
- **Admissibility score** — single 0–1 metric summarising safety behaviour
- **Guard vs no-guard diff** — collision rate, near-miss rate, task completion

Open the `.html` file in any browser. No server needed.

---

## Python API — ScenarioRunner

```python
from pathlib import Path
from partenit.safety_bench import ScenarioRunner, ScenarioConfig

runner = ScenarioRunner()
config = ScenarioConfig.from_yaml(Path("examples/benchmarks/human_crossing_path.yaml"))

# Run without guard (baseline)
result_ng = runner.run(config, with_guard=False)

# Run with guard
result_g = runner.run(config, with_guard=True)

print(result_g.admissibility_score)   # 0.0 – 1.0
print(result_g.events)                # list of SafetyEvents
print(result_g.matched_events)        # expected events that were triggered
print(result_g.missed_events)         # expected events that were NOT triggered
print(result_g.trust_curve)           # [(time, trust_level), ...]
```

---

## partenit-eval — measure your robot's safety grade

`partenit-eval` runs a scenario with multiple controllers and produces
a comparative grade (A–F) for each.

```bash
partenit-eval run examples/benchmarks/human_crossing_path.yaml \
    --report eval.html

partenit-eval run examples/benchmarks/human_crossing_path.yaml \
    --compare policies/baseline.yaml policies/v2.yaml
```

```python
from partenit.safety_bench.eval import EvalRunner, ControllerConfig

runner = EvalRunner()
report = runner.run_scenario(
    "examples/benchmarks/human_crossing_path.yaml",
    controllers=[
        ControllerConfig("baseline", policy_paths=[]),
        ControllerConfig("guarded",  policy_paths=["examples/warehouse/policies.yaml"]),
    ],
)
print(report.summary_table())
# baseline  F  safety=0.12  efficiency=0.30  overall=0.15
# guarded   B  safety=0.92  efficiency=0.78  overall=0.87
```

### Grade thresholds

| Grade | Overall score |
|---|---|
| A | ≥ 0.90 |
| B | ≥ 0.75 |
| C | ≥ 0.60 |
| D | ≥ 0.45 |
| F | < 0.45 |

### Score formula

```
safety_score     = 1 - 0.5*collision_rate - 0.3*near_miss_rate - 0.2*unsafe_acceptance_rate
efficiency_score = task_completion_rate * (1 - 0.2 * clamp_rate)
ai_score         = 1 - unsafe_acceptance_rate
overall_score    = 0.5*safety + 0.3*efficiency + 0.2*ai_score
```

---

## partenit-scenario — alias for partenit-bench

`partenit-scenario` is identical to `partenit-bench`.
Use whichever reads better in your scripts.

```bash
partenit-scenario run scenario.yaml --report report.html
```

---

## Determinism guarantee

All scenarios run with a fixed seed and produce identical output on every run.
This makes scenarios suitable for CI:

```bash
# In CI — fails if guard behaviour changes unexpectedly
partenit-bench run tests/scenarios/human_crossing.yaml \
    --with-guard --assert-grade B
```

---

## Dependencies

```
pydantic >= 2.0
numpy
rich
partenit-core >= 0.1.0
partenit-policy-dsl >= 0.1.0
partenit-trust-engine >= 0.1.0
partenit-agent-guard >= 0.1.0
```

---

[Documentation](../../../docs/) · [Examples](../../../examples/benchmarks/) · [Issues](https://github.com/GradeBuilderSL/partenit/issues)
