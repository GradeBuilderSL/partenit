[<img src="partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![Tests](https://img.shields.io/badge/tests-191%20passing-brightgreen)
![Packages](https://img.shields.io/badge/packages-7%20open--source-blue)

[![Isaac Sim](https://img.shields.io/badge/Isaac%20Sim-4.x%20%7C%205.x-76b900?logo=nvidia&logoColor=white)](examples/isaac_sim/)
[![ROS2](https://img.shields.io/badge/ROS2-Humble%20%7C%20Iron%20%7C%20Jazzy-22314E?logo=ros&logoColor=white)](partenit/packages/adapters/src/partenit/adapters/ros2.py)
[![Unitree](https://img.shields.io/badge/Unitree-H1%20%7C%20G1%20%7C%20B2-111111?logoColor=white)](partenit/packages/adapters/src/partenit/adapters/unitree/)
[![Gazebo](https://img.shields.io/badge/Gazebo-Garden%20%7C%20Harmonic-FF6B35?logoColor=white)](partenit/packages/adapters/src/partenit/adapters/gazebo/)

# Debugging & Safety Toolkit for Robot AI

Partenit is an open-source middleware between your robot's high-level AI planner and its low-level motors.
It guarantees that no action executes without formal validation, and every decision is logged with a
cryptographic fingerprint for audit.

**Install it today to:**

- Add a safety guard to your robot in **one line of code**
- Test your safety policies before deploying to hardware
- Record every robot decision for debugging and incident investigation
- Run safety scenarios in Isaac Sim, ROS2, or a pure-Python simulation
- Measure your robot's **safety grade (A–F)** against standard scenarios

---

## 5-minute quickstart

```bash
pip install partenit-core partenit-agent-guard partenit-safety-bench \
            partenit-policy-dsl partenit-decision-log partenit-adapters
```

From source: `git clone https://github.com/GradeBuilderSL/partenit.git && cd partenit && ./scripts/install.sh`

```python
from partenit.adapters import MockRobotAdapter
from partenit.agent_guard import GuardedRobot

# Prepare a scene (your adapter gives real sensor data)
adapter = MockRobotAdapter()
adapter.add_human("worker-1", x=1.2, y=0.0)   # worker 1.2 m away

# One line to add full safety guard + decision logging
robot = GuardedRobot(
    adapter=adapter,
    policy_path="examples/warehouse/policies.yaml",
    session_name="my_test",
)

decision = robot.navigate_to(zone="shipping", speed=2.0)
print(decision.allowed)               # True  (guard allows, but clamps speed)
print(decision.modified_params)       # {'zone': 'shipping', 'speed': 0.3}
print(decision.risk_score.value)      # 0.64  (human at 1.2 m → high risk)
print(decision.applied_policies)      # ['human_proximity_slowdown']
```

The guard automatically:
- fetches sensor observations from the adapter
- evaluates all policies
- clamps or blocks the action if needed
- logs a signed `DecisionPacket` for audit

Swap `MockRobotAdapter` → `IsaacSimAdapter` / `ROS2Adapter` / `HTTPRobotAdapter` — the guard stays identical.

### Use with Isaac Sim

If you develop or test robots in **NVIDIA Isaac Sim**, you get the same guard, logging, and grading with one adapter and a small bridge inside the sim. **Quick path:** start the H1 bridge in Isaac Sim (`examples/isaac_sim/h1_bridge.py`), then run `python examples/isaac_sim/minimal_guard_demo.py` to see one guarded command and the decision in the console. Full guide: [docs/guides/isaac-sim.md](docs/guides/isaac-sim.md).

---

## Why install Partenit in your robot project?

| Problem | Partenit tool |
|---------|--------------|
| "Start a new guarded robot project" | `partenit-init my_robot` — scaffold in 5 seconds |
| "My robot stopped — explain why in plain English" | `partenit-why decisions/session_01/` |
| "Show me live decisions as they happen" | `partenit-watch decisions/` — live TUI, refreshes every 500 ms |
| "My robot does something unsafe — why?" | `partenit-log replay decisions/` — visual timeline of every decision |
| "Is my controller safe?" | `partenit-eval run scenario.yaml` — grades A–F with collision/near-miss metrics |
| "Which policy fires at distance 1.2 m?" | `partenit-policy sim --human-distance 1.2 --policy-path policies/` |
| "How does v2 policy differ from v1?" | `partenit-policy diff policies/v1.yaml policies/v2.yaml` |
| "Validate policies on every PR automatically" | [GitHub Action](#github-action--ci-integration) — 3 lines of YAML |
| "I need to run a scenario in Isaac Sim" | [Isaac Sim guide](docs/guides/isaac-sim.md) + `IsaacSimAdapter` |
| "I want to compare two controllers" | `partenit-eval run scenario.yaml --compare baseline.yaml v2.yaml` |
| "How many decisions were blocked this session?" | `partenit-stats decisions/` — risk distribution, top policies, duration |
| "Export decisions to CSV / JSON for analysis" | `partenit-log export decisions/ --format csv --output dump.csv` |

---

## Toolkit overview

### 1. GuardedRobot — add a safety guard in one line

```python
from partenit.agent_guard import GuardedRobot

robot = GuardedRobot(adapter, policy_path="policies/", session_name="test")
robot.navigate_to(zone="A3", speed=2.0)   # auto-guarded, auto-logged
```

The guard intercepts every action, evaluates all policies, clamps parameters if needed,
and stores a signed decision packet. Zero changes to your robot code.

### 2. partenit-eval — measure your robot's safety grade

```bash
partenit-eval run examples/benchmarks/human_crossing_path.yaml \
    --report eval.html
```

Compare baseline (no guard) vs guarded controller on the same scenario:

```python
from partenit.safety_bench.eval import EvalRunner, ControllerConfig

runner = EvalRunner()
report = runner.run_scenario(
    "examples/benchmarks/human_crossing_path.yaml",
    controllers=[
        ControllerConfig("baseline", policy_paths=[]),
        ControllerConfig("guarded",  policy_paths=["policies/warehouse.yaml"]),
    ],
)
print(report.summary_table())
# baseline  F  safety=0.12  efficiency=0.30  overall=0.15
# guarded   B  safety=0.92  efficiency=0.78  overall=0.87
```

Metrics: collision rate, near-miss rate, min human distance, task completion,
unsafe acceptance rate, AI quality — all combined into a weighted grade (A–F).
HTML report opens in any browser, no server required.

### 3. partenit-why — explain any decision in plain English

```bash
partenit-why decisions/session_01/
```

```
╭─ Decision Explanation ──────────────────────────────╮
│  Action : navigate_to(zone='C2', speed=2.0)         │
│  Time   : 2026-03-08 14:23:41 UTC                   │
│  Status : ● BLOCKED   Risk score: 0.92              │
│                                                      │
│  Why BLOCKED:                                        │
│    → Rule fired: emergency_stop                      │
│                                                      │
│  Risk contributors:                                  │
│    human_distance              0.85  ████████████   │
│    speed                       0.45  ███████        │
│                                                      │
│  Fingerprint: ✓ VALID                               │
╰──────────────────────────────────────────────────────╯
```

Works with a single JSON file, JSONL log, or a decisions directory.

### 4. partenit-watch — live monitor of guard decisions

```bash
partenit-watch decisions/
```

```
┌─ Partenit Guard Monitor ─── session_01 ─── total=24 blocked=1 modified=6 ─┐
│  Time      Status     Action              Risk  Policies / Reason           │
│  14:23:41  BLOCKED    navigate_to         0.92  emergency_stop              │
│  14:23:39  MODIFIED   navigate_to         0.64  human_proximity_slowdown    │
│  14:23:35  ALLOWED    navigate_to         0.12                              │
└────────────────────────────────────────────────────────────────────────────┘
```

Refreshes every 500 ms as new decisions arrive. Ctrl+C to stop.

### 5. partenit-log replay — debug decisions visually

```bash
partenit-log replay decisions/my_test/      # rich terminal timeline
partenit-log replay decisions/ --output timeline.html  # shareable HTML
```

```
Decision Replay — my_test (12 packets)
──────────────────────────────────────────
 0.0s  [ALLOWED  ] navigate_to  speed=1.5  risk=0.21
 2.1s  [MODIFIED ] navigate_to  speed=0.3  risk=0.64  → human_proximity_slowdown
 3.0s  [BLOCKED  ] navigate_to            risk=0.91  → emergency_stop
```

### 6. partenit-policy sim — test policies interactively

```bash
partenit-policy sim \
    --action navigate_to \
    --speed 2.0 \
    --human-distance 1.2 \
    --policy-path examples/warehouse/policies.yaml
```

Shows exactly which rules fire, what parameters are clamped, and the final allowed/blocked result.
No hardware, no simulation — instant feedback.

### 7. partenit-policy diff — compare two policy versions

```bash
partenit-policy diff policies/v1.yaml policies/v2.yaml
partenit-policy diff policies/v1/ policies/v2/ \
    --scenario examples/benchmarks/human_crossing_path.yaml
```

```
Policy diff: policies/v1.yaml → policies/v2.yaml
─────────────────────────────────────────────────
  + human_proximity_slowdown    (added)
  ~ emergency_stop              (changed: threshold 0.5 → 0.8)
  = speed_limit_zone_a          (unchanged)

Scenario impact (human_crossing_path):
  Metric              v1      v2      Δ
  block_rate         0.10    0.30   +0.20
  near_miss_rate     0.40    0.15   -0.25
```

Immediately see what changed between policy versions and how it affects safety outcomes.

### 8. partenit-scenario / partenit-bench — run safety scenarios

```bash
partenit-scenario run examples/benchmarks/human_crossing_path.yaml \
    --with-guard --without-guard \
    --report report.html
```

Built-in scenarios:
- `human_crossing_path` — worker crosses robot trajectory
- `blind_spot` — human in low-confidence detection zone
- `llm_unsafe_command` — LLM requests unsafe speed near a human
- `sensor_degradation` — trust degrades mid-mission; conservative fallback
- `policy_conflict_determinism` — priority-based conflict resolution (100% deterministic)

---

## Supported platforms

The guard and policies are **identical** across all platforms — only the adapter changes:

| Platform | Adapter |
|----------|---------|
| Pure Python (no hardware) | `MockRobotAdapter` |
| Any HTTP robot | `HTTPRobotAdapter` |
| ROS2 | `ROS2Adapter` |
| NVIDIA Isaac Sim | `IsaacSimAdapter` |
| Unitree robots | `UnitreeAdapter` |
| Gazebo | `GazeboAdapter` |
| LLM tool calls | `LLMToolCallGuard` |
| MoveIt / Open RMF | *Planned* — stubs only, not functional yet |

```python
# Development / simulation
adapter = MockRobotAdapter()

# Real ROS2 robot — only this line changes
adapter = ROS2Adapter(node_name="partenit_guard")

# Isaac Sim (H1 bridge example uses port 8000)
adapter = IsaacSimAdapter(base_url="http://localhost:8000")

# Everything below is identical regardless of adapter
robot = GuardedRobot(adapter, policy_path="policies/warehouse.yaml")
decision = robot.navigate_to(zone="shipping", speed=1.8)
```

---

## Policy DSL — write safety rules in YAML

```yaml
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

Validate, bundle, and check for conflicts:

```bash
partenit-policy validate ./policies/
partenit-policy check-conflicts ./policies/
partenit-policy bundle ./policies/ --output bundle.json
```

---

## Decision audit trail

Every action — allowed, clamped, or blocked — produces a signed `DecisionPacket`:

```python
from partenit.decision_log import DecisionLogger

log = DecisionLogger(storage_dir="decisions/session_01")
packet = log.create_packet(
    action_requested="navigate_to",
    action_params={"zone": "shipping", "speed": 2.0},
    guard_decision=decision,
)
print(log.verify_packet(packet))   # True — SHA256 fingerprint verified
```

Verify integrity after the fact:
```bash
partenit-log verify decisions/session_01/
partenit-log inspect <packet_id>
```

---

## Repository layout

```
partenit/
├── packages/
│   ├── core/           # Shared types and contracts (Pydantic v2)
│   ├── policy-dsl/     # YAML policy language + parser + validator
│   ├── trust-engine/   # Sensor/object trust degradation model
│   ├── agent-guard/    # GuardedRobot + action safety middleware
│   ├── safety-bench/   # Simulation sandbox + scenario runner + eval
│   ├── decision-log/   # DecisionPacket format + storage + verification
│   └── adapters/       # Robot adapters: Mock, ROS2, HTTP, Isaac Sim, …
├── analyzer/           # Web UI: FastAPI backend + React frontend
├── schemas/            # JSON Schemas and OpenAPI spec
├── docs/               # Guides and reference documentation
└── examples/           # Runnable demos
```

---

## Open vs Enterprise

**Open in this repository:**
- Policy DSL + policy engine
- Basic risk scoring (distance + velocity + trust)
- Mock / HTTP / ROS2 / Isaac Sim / Unitree / Gazebo adapters
- Safety bench + all built-in scenarios
- Decision log + fingerprint verification
- Analyzer web UI
- JSON Schemas for `DecisionPacket` and `DecisionFingerprint`
- All examples and documentation

**Enterprise (closed, not in this repo):**
- Conformal prediction with coverage guarantees
- Plan-conditional risk scoring
- GraphRAG policy retrieval
- Formal verification (CBF / STL)
- Fleet coordination and policy broadcast
- Cloud sync and managed storage
- Compliance export tooling (ISO, audit documents)
- Policy authoring UI

---

## GitHub Action — CI integration

Add automatic safety checks to any robot project in 3 lines:

```yaml
# .github/workflows/safety.yml
name: Safety Check
on:
  push:
    paths: ['policies/**']
  pull_request:
    paths: ['policies/**']

jobs:
  safety:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: GradeBuilderSL/partenit@main
        with:
          policy-path: policies/
```

Every pull request that modifies policies will automatically:
- Validate YAML syntax and policy semantics
- Detect conflicting rules (PR fails if conflicts are found)

Add `scenario:` to run a safety simulation and upload an HTML report:

```yaml
      - uses: GradeBuilderSL/partenit@v1
        with:
          policy-path: policies/
          scenario: tests/scenarios/human_crossing.yaml
```

Enforce a minimum safety grade — **fail the PR if your controller drops below B:**

```yaml
      - uses: GradeBuilderSL/partenit@v1
        id: safety
        with:
          policy-path: policies/
          scenario: tests/scenarios/human_crossing.yaml
          min-grade: B          # A / B / C / D — fail if below
      - run: echo "Grade ${{ steps.safety.outputs.safety-grade }}, score ${{ steps.safety.outputs.overall-score }}"
```

**Action inputs:**

| Input | Default | Description |
|---|---|---|
| `policy-path` | `policies/` | Path to policy file or directory |
| `scenario` | — | Scenario YAML for safety simulation (optional) |
| `min-grade` | — | Minimum grade: `A`, `B`, `C`, or `D`. Fails if below. |
| `python-version` | `3.11` | Python version |
| `fail-on-conflict` | `true` | Exit 1 if conflicting policies found |
| `report-name` | `partenit-safety-report` | Artifact name for HTML report |

**Action outputs:**

| Output | Description |
|---|---|
| `result` | `passed` or `failed` |
| `safety-grade` | Letter grade of the guarded controller: A / B / C / D / F |
| `overall-score` | Weighted overall score 0.0–1.0 |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, architecture rules, and the PR process.
See [docs/](docs/) for full guides on Isaac Sim, ROS2, custom robots, and writing policies.
See [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) for a release checklist and the two main user paths (no hardware + simulation).

[<img src="partenit_robot.png" alt="Partenit robot" width="320" />](https://partenit.io)

Made with love for the future at [Partenit](https://partenit.io).
