# partenit

> **Safety and decision infrastructure for robot AI.**
> One install. All tools. Works in simulation and on real hardware.

```bash
pip install partenit
```

---

## What you get

| Package | What it does |
|---|---|
| `partenit-core` | Shared data contracts: `GuardDecision`, `DecisionPacket`, `PolicyRule` |
| `partenit-policy-dsl` | YAML safety policies + validator + CLI |
| `partenit-trust-engine` | Sensor trust degradation model |
| `partenit-agent-guard` | Action safety middleware — validates every command before execution |
| `partenit-adapters` | Robot adapters: Mock, HTTP, ROS2, Isaac Sim, Unitree, Gazebo |
| `partenit-decision-log` | Audit log with SHA-256 fingerprints + replay tools |
| `partenit-safety-bench` | Scenario runner + safety evaluator + HTML reports |

---

## Quickstart

```python
from partenit.adapters import MockRobotAdapter
from partenit.agent_guard import GuardedRobot

robot = GuardedRobot(
    MockRobotAdapter(),
    policy_path="examples/warehouse/policies.yaml",
    session_name="my_run",
)

decision = robot.navigate_to(zone="shipping", speed=2.0)
print(decision.allowed)           # True / False
print(decision.risk_score.value)  # 0.0 – 1.0
print(decision.applied_policies)  # which rules fired
```

---

## CLI tools

```bash
# Explain why the robot stopped
partenit-why decisions/session_01/

# Watch live guard decisions
partenit-watch decisions/

# Replay a session in terminal
partenit-log replay decisions/session_01/

# Test your policies interactively
partenit-policy sim --action navigate_to --speed 2.0 --human-distance 1.2

# Run a safety scenario
partenit-bench run examples/benchmarks/human_crossing_path.yaml

# Get a safety grade (A–F) for your controller
partenit-eval run examples/benchmarks/ --report eval.html
```

---

## Why Partenit?

**Robots make decisions. You should understand them.**

Partenit sits between your controller and your robot:

```
LLM / Planner
     ↓
 AgentGuard  ← validates every action against safety policies
     ↓
  Adapter    ← translates to ROS2 / HTTP / Isaac Sim / Mock
     ↓
   Robot
```

Every decision is logged with a cryptographic fingerprint.
Every blocked or modified command is explainable.
Same code runs in simulation and on real hardware.

---

## Install options

```bash
pip install partenit           # all packages
pip install partenit[http]     # + HTTP robot support
pip install partenit[all]      # + rich terminal UI + Prometheus metrics
```

Or install individual packages:

```bash
pip install partenit-core           # types only
pip install partenit-agent-guard    # guard middleware
pip install partenit-safety-bench   # simulation + benchmarks
```

---

[Documentation](https://github.com/GradeBuilderSL/partenit/tree/main/docs) ·
[Examples](https://github.com/GradeBuilderSL/partenit/tree/main/examples) ·
[Issues](https://github.com/GradeBuilderSL/partenit/issues)
