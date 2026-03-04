[<img src="../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# Simulation Guide

This guide shows how to use `partenit-safety-bench` and `MockRobotAdapter`
to simulate robots and humans, run built-in safety scenarios, and compare
behavior with and without the guard.

---

## Overview

The simulation stack has three layers:

```
partenit-safety-bench       ← scenario loader + runner
        ↓
partenit-adapters           ← MockRobotAdapter (no hardware needed)
        ↓
partenit-agent-guard        ← evaluates each timestep
```

No hardware, no ROS2, no Docker required.

---

## MockRobotAdapter

`MockRobotAdapter` simulates a robot environment in memory.
Add humans and objects, then retrieve structured observations.

```python
from partenit.adapters import MockRobotAdapter

adapter = MockRobotAdapter(robot_id="sim-robot-1")

# Add a human 1.2 m ahead of the robot
adapter.add_human("worker-1", x=1.2, y=0.0)

# Add a non-human object
adapter.add_object("pallet-1", class_label="pallet", x=3.0, y=0.5)

# Get StructuredObservation list (same type as from real sensors)
observations = adapter.get_observations()

for obs in observations:
    print(obs.object_id, obs.class_best, obs.distance(), obs.treat_as_human)
# worker-1  human   1.2  True
# pallet-1  pallet  3.0  False
```

---

## Running the Guard Against Observations

```python
from partenit.adapters import MockRobotAdapter
from partenit.agent_guard import AgentGuard

adapter = MockRobotAdapter()
adapter.add_human("worker-1", x=1.2, y=0.0)

guard = AgentGuard()
guard.load_policies("examples/warehouse/policies.yaml")

observations = adapter.get_observations()

# Build context from observations
context: dict = {}
for obs in observations:
    if obs.treat_as_human:
        d = obs.distance()
        existing = context.get("human", {})
        if not existing or d < existing.get("distance", float("inf")):
            context["human"] = {"distance": d, "object_id": obs.object_id}

decision = guard.check_action(
    action="navigate_to",
    params={"zone": "shipping", "speed": 2.0},
    context=context,
    observations=observations,
)

print(decision.allowed)           # True (speed will be clamped)
print(decision.modified_params)   # {'zone': 'shipping', 'speed': 0.3}
print(decision.risk_score.value)  # ~0.69
print(decision.applied_policies)  # ['human_proximity_slowdown']
```

---

## Scenario YAML Format

Safety scenarios are defined in YAML and executed by `ScenarioRunner`.

```yaml
# examples/warehouse/human_crossing.yaml
scenario_id: human_crossing_path
duration: 15.0       # seconds of simulated time
dt: 0.1              # simulation timestep

robot:
  start_position: [0, 0, 0]
  goal_position: [10, 0, 0]
  initial_speed: 1.5

world:
  humans:
    - id: human_01
      start_position: [5, 3, 0]
      velocity: [0, -1, 0]       # moving toward robot path
      appears_at: 2.0            # enters the scene at t=2s
      confidence: 0.9

  objects:
    - id: shelf-1
      class: shelf
      position: [8, 2, 0]

policies:
  - "./policies/warehouse.yaml"

expected_events:
  - at_time: 2.5
    event: slowdown
  - at_time: 3.0
    event: stop
    condition: human.distance < 0.8
```

### World fields

| Field | Description |
|---|---|
| `humans[].id` | Unique identifier |
| `humans[].start_position` | `[x, y, z]` in meters |
| `humans[].velocity` | `[vx, vy, vz]` in m/s |
| `humans[].appears_at` | Simulation time when the human enters the scene |
| `humans[].confidence` | Initial detection confidence (0.0–1.0) |
| `objects[].class` | Object class label (`shelf`, `obstacle`, etc.) |

---

## Running Scenarios Programmatically

```python
from partenit.safety_bench import ScenarioRunner

runner = ScenarioRunner()
config = runner.load("examples/warehouse/human_crossing.yaml")

# Run WITH guard
result_with = runner.run(config, with_guard=True, log_decisions=True)
print(result_with.summary())

# Run WITHOUT guard (baseline)
result_without = runner.run(config, with_guard=False)
print(result_without.summary())
```

Example output:

```
Scenario: human_crossing_path (with guard)
  Duration:  11.3s simulated | 42ms wall
  Decisions: 113 total | 8 blocked (7%) | 31 modified
  Goal:      reached
  Events:    39
  Matched:   slowdown@2.5s, stop@3.0s

Scenario: human_crossing_path (NO guard)
  Duration:  6.7s simulated | 18ms wall
  Decisions: 0 total | 0 blocked (0%) | 0 modified
  Goal:      reached
  Events:    0
```

---

## Running Scenarios via CLI

```bash
# Install the bench package
pip install partenit-safety-bench

# Run a single scenario
partenit-bench run examples/warehouse/human_crossing.yaml

# Run all scenarios in a directory (with and without guard)
partenit-bench run-all examples/warehouse/ --with-guard --without-guard

# Generate HTML report
partenit-bench run-all examples/warehouse/ --output report.html
```

---

## Comparing Guard vs No-Guard

The most common use is a side-by-side comparison to validate that the guard
correctly modifies or blocks dangerous actions:

```python
runner = ScenarioRunner()
config = runner.load("my_scenario.yaml")

with_guard    = runner.run(config, with_guard=True)
without_guard = runner.run(config, with_guard=False)

print(f"Guard block rate:     {with_guard.block_rate:.0%}")
print(f"No-guard block rate:  {without_guard.block_rate:.0%}")
print(f"Guard reached goal:   {with_guard.reached_goal}")
```

---

## Built-in Scenarios

The `examples/warehouse/` directory ships with five ready-to-run scenarios:

| Scenario ID | What it tests |
|---|---|
| `human_crossing_path` | Human crosses robot trajectory |
| `degraded_sensor` | Trust drops mid-mission |
| `policy_conflict` | Two rules fire simultaneously |
| `blind_spot` | Human in low-confidence zone |
| `llm_unsafe_command` | LLM requests dangerous speed |

---

## What to Read Next

- [Writing policies](writing-policies.md) — define your own safety rules
- [LLM agent guard](llm-agent.md) — use the guard with Claude or GPT tool calls
- [Custom robot (HTTP)](custom-robot.md) — connect real hardware

---

## Using Partenit with full simulators (Isaac / Gazebo)

`partenit-safety-bench` and `MockRobotAdapter` give you a **pure Python** sandbox.
When you are ready to plug into a full simulator, you keep the same guard code and
change only the adapter:

### Isaac Sim via `IsaacSimAdapter`

```python
from pathlib import Path

from partenit.adapters.isaac_sim import IsaacSimAdapter
from partenit.agent_guard import AgentGuard

adapter = IsaacSimAdapter(base_url="http://localhost:7000", robot_id="isaac-sim-demo")

guard = AgentGuard()
guard.load_policies(Path("examples/warehouse/policies.yaml"))

observations = adapter.get_observations()
decision = guard.check_action(
    action="navigate_to",
    params={"zone": "shipping", "speed": 1.8},
    context={"source": "isaac_sim"},
    observations=observations,
)

adapter.send_decision(decision)
```

In this setup, a small Isaac Sim extension (or sidecar service) exposes the
standard HTTP API described in the **Custom Robot (HTTP)** guide. No changes are
required in the Partenit core.

### Gazebo and other simulators

For Gazebo and similar simulators you have two options:

- **ROS2 path** — use `ROS2Adapter` if your sim already publishes robot state to ROS2 topics.
- **HTTP gateway** — run a tiny HTTP service that reads sim state and implements the same
  `/partenit/observations`, `/partenit/command`, `/partenit/health` contract.

In both cases the simulation ↔ Partenit boundary is **just an adapter**. Your policies,
trust model, guard code, and Analyzer remain unchanged.
