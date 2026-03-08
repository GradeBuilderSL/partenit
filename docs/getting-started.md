[<img src="../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# Getting Started with Partenit

This guide takes you from zero to your first cryptographically-logged safety decision in under 15 minutes.

## What you'll build

A warehouse robot scenario where:
1. A worker stands 1.2 m from the robot
2. An LLM (or your planner) proposes a fast navigation command
3. **Partenit** intercepts the command, clamps the speed, and logs the decision
4. The audit record has a SHA-256 fingerprint — tamper-evident, forever

---

## Prerequisites

- Python 3.11+
- `pip` (or `uv`)

---

## Installation

```bash
pip install partenit-core partenit-agent-guard partenit-adapters partenit-decision-log
```

Optional, for running built-in scenarios:

```bash
pip install partenit-safety-bench
```

---

## 5-line quick start

```python
from partenit.adapters import MockRobotAdapter
from partenit.agent_guard import AgentGuard

adapter = MockRobotAdapter()
adapter.add_human("worker-1", x=1.2, y=0.0)
guard = AgentGuard()
guard.load_policies("examples/warehouse/policies.yaml")

obs = adapter.get_observations()
decision = guard.check_action(
    action="navigate_to",
    params={"zone": "shipping", "speed": 2.0},
    context={"human": {"distance": 1.2}},
    observations=obs,
)

print(decision.allowed)           # True (speed will be clamped)
print(decision.modified_params)   # {'zone': 'shipping', 'speed': 0.3}
print(decision.risk_score.value)  # 0.69 (high risk → speed reduced)
```

---

## Step 1: Run the two examples

Run the baseline unsafe example:

```bash
python examples/robot_without_guard.py
```

Output:
```
=== NO GUARD — Baseline Unsafe Behavior ===
  worker-1: human @ 1.2m (treat_as_human=True)
  pallet-1: pallet @ 3.0m (treat_as_human=False)

Executing: navigate_to {'zone': 'shipping', 'speed': 2.0}
  → No safety check performed
  → Speed: 2.0 m/s (UNSAFE near human at 1.2m)
```

Now run with the guard:

```bash
python examples/robot_with_guard.py
```

Output:
```
=== WITH GUARD — Safe Behavior ===

Requested: navigate_to {'zone': 'shipping', 'speed': 2.0}

✓ ALLOWED — executing with params: {'zone': 'shipping', 'speed': 0.3}
  Applied policies: ['human_proximity_slowdown']
  Risk score: 0.69
  Speed clamped: 2.0 → 0.3 m/s

DecisionPacket: 3fa8c21d-...
Fingerprint:    a7f3b2e1...
Verified:       True
```

Same scenario. With guard: speed is safely clamped and the decision is logged.

---

## Step 2: Write your first policy

Policies live in YAML. Safety engineers can write them without code.

```yaml
# my_policy.yaml
rule_id: human_proximity_slowdown
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
  parameter: max_velocity
  value: 0.3
  unit: m/s
```

Load it:

```python
guard = AgentGuard()
guard.load_policies("my_policy.yaml")
```

Validate it from the CLI:

```bash
partenit-policy validate my_policy.yaml
```

---

## Step 3: Log every decision

Every decision should produce a `DecisionPacket` — your tamper-evident audit record.

```python
from partenit.decision_log import DecisionLogger

log = DecisionLogger(storage_dir="./decisions/")

packet = log.create_packet(
    action_requested="navigate_to",
    action_params={"zone": "shipping", "speed": 2.0},
    guard_decision=decision,
)

print(packet.fingerprint)           # SHA-256 of the full packet
print(log.verify_packet(packet))    # True — always, unless tampered
```

Inspect from the CLI:

```bash
partenit-log verify ./decisions/
partenit-log inspect <packet_id>
```

---

## Step 4: Run a safety scenario

```bash
partenit-bench run examples/warehouse/human_crossing.yaml
```

This runs the full simulation: robot navigates toward goal, human crosses the path,
guard fires, speed is clamped.

---

## Step 5: Start the Analyzer

```bash
cd analyzer && docker-compose up
# open http://localhost:3000
```

The Analyzer lets you:
- Visualize risk score timelines
- Inspect any `DecisionPacket` and verify its fingerprint
- Browse active policies and detected conflicts
- Run live guard checks from the browser UI

---

## Architecture at a glance

```
Your Planner / LLM
        ↓  proposes action
   AgentGuard          ← partenit-agent-guard
        ↓  evaluates policies + computes risk
  PolicyEvaluator      ← partenit-policy-dsl
  RiskScorer           ← partenit-agent-guard
        ↓  returns GuardDecision
  DecisionLogger       ← partenit-decision-log
        ↓  creates DecisionPacket + fingerprint
   Your Robot          ← partenit-adapters
        ↓  executes (or skips) the action
```

**Nothing executes without a decision. Nothing is decided without a log.**

---

## What's next?

- [Writing policies](guides/writing-policies.md) — full YAML reference for safety engineers
- [Simulation guide](guides/simulation.md) — using MockRobot and built-in scenarios
- [Isaac Sim guide](guides/isaac-sim.md) — **verify your controller in simulation**: same guard, logs, and grades with the H1 bridge
- [ROS2 integration](guides/ros2-robot.md) — plug into a real robot
- [LLM agent guard](guides/llm-agent.md) — intercept tool calls from Claude, GPT, etc.
- [Custom robot (HTTP)](guides/custom-robot.md) — any robot with a REST API
