# CLAUDE.md — Partenit Project

## What is Partenit

Partenit is an open-source safety and cognitive control infrastructure
for physical AI agents — robots, LLM agents, and autonomous systems.

It is a middleware layer between a high-level planner (mission/task)
and a low-level controller (nav/motors). It guarantees that no action
is executed without formal validation, and every decision is logged
with a cryptographic fingerprint for audit.

**Core philosophy:**
- LLM generates hypotheses. Partenit decides if they are admissible.
- Every decision must be reproducible, explainable, and auditable.
- Works in simulation and on real robots without code changes.
- Hardware-agnostic via adapter pattern. No lock-in to ROS or any
  specific robot vendor.

---

## Repository Structure

```
partenit/
├── packages/
│   ├── core/           # Shared types, contracts, base classes (Pydantic v2)
│   ├── policy-dsl/     # YAML policy language + parser + validator
│   ├── trust-engine/   # Sensor/object trust degradation model
│   ├── agent-guard/    # Action safety middleware (LLM, ROS2, HTTP)
│   ├── safety-bench/   # Simulation sandbox + scenario runner
│   ├── decision-log/   # DecisionPacket format + storage + verification
│   └── adapters/       # Robot adapters: Mock, ROS2, HTTP
├── analyzer/
│   ├── backend/        # FastAPI server
│   └── frontend/       # React + TypeScript + Tailwind + recharts
├── schemas/
│   ├── DecisionPacket.schema.json
│   ├── DecisionFingerprint.schema.json
│   └── robot-adapter-api.yaml  # OpenAPI spec for vendor integration
├── docs/
│   ├── getting-started.md
│   ├── guides/
│   │   ├── simulation.md
│   │   ├── ros2-robot.md
│   │   ├── custom-robot.md
│   │   ├── llm-agent.md
│   │   └── writing-policies.md
│   ├── reference/
│   │   ├── decision-packet.md
│   │   └── trust-model.md
│   └── vendor/
│       └── robot-adapter-spec.md
├── examples/
│   ├── robot_without_guard.py
│   ├── robot_with_guard.py
│   ├── llm_agent_guard_demo.py
│   └── warehouse/
└── tests/
```

---

## Package Dependency Order

Always build and import in this order:

```
partenit-core
    ↓
partenit-policy-dsl
partenit-trust-engine
    ↓
partenit-agent-guard
partenit-adapters
    ↓
partenit-safety-bench
partenit-decision-log
    ↓
partenit-analyzer (backend + frontend, build last)
```

---

## Core Data Contracts

These types are defined in `partenit-core` and used everywhere.
Never redefine them in other packages — always import from core.

### Key types:
- `StructuredObservation` — sensor output, one detected object
- `PolicyRule` — one safety rule with priority and provenance
- `PolicyBundle` — versioned collection of PolicyRule
- `RiskScore` — float 0-1 with feature attribution dict
- `GuardDecision` — allowed/blocked + modified params + reason
- `TrustState` — per-sensor trust level + degradation reasons
- `SafetyEvent` — stop/slowdown/violation event
- `DecisionPacket` — full audit record for one decision cycle
- `DecisionFingerprint` — SHA256 hash of DecisionPacket

**DecisionPacket is the open standard.**
Its JSON Schema lives in `/schemas/` and must never have
breaking changes without a major version bump.

---

## Architecture: Two Loops

### Fast Path — Edge Node (target: Kria KV260 or any edge device)
- Runs: perception-edge, trust-edge, safety-edge
- Latency budget: p99 < 50ms
- Must work autonomously if cognitive node is down
- Outputs: StructuredObservation stream, SafetyEvents
- Hard requirement: safety-edge enforces stop/slowdown
  even with no cognitive node present

### Slow Path — Cognitive Node (Orin NX / NUC / server)
- Runs: world-memory, policy-rag, planner, risk-engine,
        constraint-solver, decision-log
- Latency budget: 0.5-5 seconds
- Outputs: GuardDecision, DecisionPacket

**These two loops are independent.**
Fast path protects against immediate physical harm.
Slow path handles reasoning, planning, and audit.

---

## Adapter Pattern — Hardware Agnostic

All robot-specific code lives in `partenit-adapters`.
Core packages have zero knowledge of any robot or simulator.

### RobotAdapter interface (adapters/base.py):
```python
class RobotAdapter(ABC):
    def get_observations(self) -> list[StructuredObservation]: ...
    def send_decision(self, decision: GuardDecision) -> bool: ...
    def get_health(self) -> dict: ...
    def is_simulation(self) -> bool: ...
```

### Available adapters:
- `MockRobotAdapter` — simulation, no hardware needed
- `HTTPRobotAdapter` — any robot with REST API
- `ROS2Adapter` — optional, graceful ImportError if rclpy absent

### HTTPRobotAdapter vendor contract:
Robot must expose exactly these endpoints:
```
GET  /partenit/observations  ->  StructuredObservation[]
POST /partenit/command       <-  GuardDecision
GET  /partenit/health        ->  {status, robot_id, timestamp}
```
OpenAPI spec: `/schemas/robot-adapter-api.yaml`

### Simulation to real robot — same code:
```python
# Development / simulation
adapter = MockRobotAdapter()

# Real ROS2 robot — only this line changes
adapter = ROS2Adapter(node_name="partenit_guard")

# Any vendor robot
adapter = HTTPRobotAdapter(base_url="http://192.168.1.100")

# Everything below is identical regardless of adapter
obs = adapter.get_observations()
decision = guard.check(obs, action="navigate", params={...})
adapter.send_decision(decision)
```

---

## Policy DSL

Policies are written in YAML by safety engineers (not developers).
Parser lives in `partenit-policy-dsl`.

### Format:
```yaml
rule_id: human_proximity_slowdown
name: "Human Proximity Speed Limit"
priority: safety_critical        # safety_critical | legal | task | efficiency
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
release:
  type: compound
  conditions:
    - metric: human.distance
      operator: greater_than
      value: 2.0
    - elapsed_seconds: 3
```

### Priority hierarchy (conflict resolution):
```
safety_critical  >  legal  >  task  >  efficiency
```
Higher priority always wins. This is deterministic and logged.

### CLI:
```bash
partenit-policy validate ./policies/
partenit-policy bundle ./policies/ --output bundle.json
partenit-policy check-conflicts ./policies/
```

---

## Trust Engine

`partenit-trust-engine` models two types of trust degradation.

### Sensor trust (SensorTrustModel):
```
Trust(t+1) = Trust(t) * decay_factor + reinforcement
```
Degradation triggers: depth_variance spike, low lighting,
inconsistent detections, noise spikes, frame rate drops.

Thresholds:
- nominal:    trust > 0.8
- degraded:   0.5 - 0.8
- unreliable: 0.2 - 0.5
- failed:     < 0.2

### Object confidence (ObjectConfidenceModel):
```
confidence(t) = confidence(t0) * exp(-lambda * time_since_seen)
```
lambda is configurable per class. Humans decay faster than furniture.
Below 0.1 → mark as location_uncertain.

### Conformal prediction bridge:
If "human" appears in the prediction set → treat_as_human = True.
Conservative by design: uncertainty is resolved toward safety.

---

## Agent Guard

`partenit-agent-guard` intercepts every action before execution.
Works for LLM tool calls, ROS2 skill calls, any function call.

### What guard does:
1. Receives: action name + params + context
2. Checks: all applicable PolicyRules
3. Computes: RiskScore
4. Returns: GuardDecision (allow / block / modify params)

### GuardDecision includes:
- `allowed: bool`
- `modified_params: dict | None` — guard can rewrite params safely
- `rejection_reason: str | None`
- `risk_score: RiskScore`
- `applied_policies: list[str]`
- `suggested_alternative: dict | None`

### Usage:
```python
guard = AgentGuard()
guard.load_policies("./policies/warehouse.yaml")

result = guard.check_action(
    action="navigate_to",
    params={"zone": "A3", "speed": 2.0},
    context={"humans_nearby": 1, "distance": 1.2}
)

if result.allowed:
    execute(result.modified_params)  # speed may be clamped
else:
    return result.rejection_reason
```

---

## Safety Bench

`partenit-safety-bench` runs scenarios without real hardware.

### Scenario YAML format:
```yaml
scenario_id: human_crossing_path
robot:
  start_position: [0, 0, 0]
  goal_position: [10, 0, 0]
  initial_speed: 1.0
world:
  humans:
    - id: human_01
      start_position: [5, 3, 0]
      arrival_time: 2.0
policies: ["human_proximity_slowdown", "emergency_stop"]
expected_events:
  - at_time: 2.5
    event: slowdown
  - at_time: 3.0
    event: stop
    condition: human.distance < 0.8
```

### Built-in scenarios:
1. `human_crossing_path`   — human crosses robot trajectory
2. `degraded_sensor`       — trust drops during mission
3. `policy_conflict`       — two rules fire simultaneously
4. `blind_spot`            — human in low-confidence zone
5. `llm_unsafe_command`    — LLM requests unsafe speed

### CLI:
```bash
partenit-bench run ./scenarios/human_crossing.yaml
partenit-bench run-all ./scenarios/ --with-guard --without-guard
partenit-bench report --output report.html
```

---

## Decision Log

`partenit-decision-log` creates, stores and verifies DecisionPackets.

### DecisionPacket contains:
- Input snapshot refs (observation hashes)
- Selected plan + repaired plan
- Violations checked + conflicts resolved
- Risk score + contributors
- Policies applied + provenance
- Latency breakdown per stage
- `fingerprint`: SHA256 of all above + all version strings

### Fingerprint verification:
```python
logger = DecisionLogger()
packet = logger.create_packet(...)
assert logger.verify_packet(packet)  # always true if untampered
```

### CLI:
```bash
partenit-log verify ./decisions/
partenit-log report ./decisions/ --from 2025-01-01 --output report.md
partenit-log inspect <packet_id>
```

**DecisionPacket must always be created — even on safe stop.**
There is no code path that skips logging.

---

## Analyzer (Web UI)

Full-stack tool for visualizing guard decisions and system state.

### Run:
```bash
cd analyzer && docker-compose up
# open http://localhost:3000
```

### Pages:
- **Dashboard**          — risk timeline, blocked %, sensor health cards
- **Decision Inspector** — full DecisionPacket, verify fingerprint
- **Policy Viewer**      — active rules, conflict warnings
- **Trust Monitor**      — per-sensor gauges, object confidence heatmap
- **Scenario Replayer**  — step through scenario, with/without guard
- **Live Guard Tester**  — send action+context, see GuardDecision live

### Stack:
- Backend:  FastAPI + uvicorn, reads from decision-log storage
- Frontend: React + TypeScript + Vite + Tailwind + recharts + shadcn/ui
- Theme:    dark
- Auth:     none (local tool)

---

## What is Open vs Enterprise

### Open (this repository):
- All packages listed above
- Policy DSL + basic policy engine
- Basic risk scoring (distance + velocity + trust)
- MockRobot + HTTP + ROS2 adapters
- Safety bench + all built-in scenarios
- Decision log + fingerprint verification
- Analyzer web UI
- JSON schemas for DecisionPacket and DecisionFingerprint
- All examples and documentation

### Enterprise (closed, not in this repo):
- Conformal prediction with guaranteed coverage
- Plan-conditional risk scoring
- GraphRAG policy retrieval
- CBF / STL formal verification engine
- Fleet coordination + policy broadcast
- Cloud sync + managed storage
- Compliance export (ISO, audit documents)
- Policy authoring UI
- Hardware licensing binding

---

## Development Rules

### Python packages:
- Use `pyproject.toml` with `hatch` or `uv`
- Pydantic v2 for all data models — no exceptions
- Type hints on all public functions
- pytest, target >80% coverage per package
- Each package installable standalone: `pip install partenit-core`

### Dependencies — keep minimal:
```
partenit-core:          pydantic
partenit-policy-dsl:    pydantic, pyyaml
partenit-trust-engine:  pydantic, numpy
partenit-agent-guard:   pydantic
partenit-adapters:      pydantic (rclpy optional)
partenit-safety-bench:  pydantic, numpy, rich
partenit-decision-log:  pydantic, jsonlines
analyzer backend:       fastapi, uvicorn, partenit-*
analyzer frontend:      react, typescript, tailwind, recharts, shadcn/ui
```

### Schemas:
- `/schemas/DecisionPacket.schema.json` — auto-generated from Pydantic
- `/schemas/robot-adapter-api.yaml`     — hand-written OpenAPI
- Schema changes require version bump and migration note

### Testing requirement:
Integration tests must verify that identical scenario produces
identical GuardDecision on MockRobotAdapter and HTTPRobotAdapter
(with mock HTTP server). Same code, same output — different adapter.

### Observability:
- OpenTelemetry traces on all service boundaries
- Prometheus metrics: decisions/sec, block_rate, p99_latency
- Grafana dashboard config in `/monitoring/`

### No breaking changes to:
- DecisionPacket schema (open standard)
- RobotAdapter interface
- PolicyRule schema
- CLI command signatures

These are public contracts. Deprecate with warning, remove only in next major.

---

## Acceptance Criteria

Before any release, verify:

- [ ] Edge node: p99 latency within budget (<50ms)
- [ ] Safety-edge continues stop/slowdown with cognitive node offline
- [ ] "human" in conformal set → treated as human in all code paths
- [ ] Conflict between two rules → deterministic result by priority
- [ ] DecisionPacket created on every decision, including safe stop
- [ ] Mode switch Shadow→Advisory→Full without restart or unsafe gap
- [ ] Policy retrieval not in fast loop hot path
- [ ] Policy provenance preserved end-to-end into DecisionPacket
- [ ] `partenit-log verify` passes on all generated packets
- [ ] Same scenario: MockAdapter and HTTPAdapter → same GuardDecision

---

## Deployment Modes

### Shadow Mode
Guard runs, computes decisions, logs everything.
Does not influence robot commands.
Use for: baseline data collection, initial validation.

### Advisory Mode
Safety-edge can stop/slowdown on hard constraint violations.
Core provides recommendations visible to operator.
Use for: supervised pilot, operator training.

### Full Mode
Core issues final commands.
Safety-edge remains last shield on every cmd_vel.
Use for: production after successful advisory period.

Mode switch:
```bash
POST /mode {"mode": "advisory"}
```
No restart required. No unsafe gap during switch.

---

## Quick Start

```python
pip install partenit-core partenit-agent-guard partenit-safety-bench

from partenit.adapters import MockRobotAdapter
from partenit.agent_guard import AgentGuard

adapter = MockRobotAdapter()
guard = AgentGuard()
guard.load_policies("./examples/warehouse/policies.yaml")

obs = adapter.get_observations()
decision = guard.check_action(
    action="navigate_to",
    params={"zone": "shipping", "speed": 1.5},
    context=obs
)

print(decision.allowed)           # True or False
print(decision.modified_params)   # speed may be clamped
print(decision.risk_score.value)  # 0.0 - 1.0
```

Run a safety scenario:
```bash
partenit-bench run ./examples/warehouse/human_crossing.yaml
```

Start the analyzer:
```bash
cd analyzer && docker-compose up
# open http://localhost:3000
```

---

## Links

- Getting started:       /docs/getting-started.md
- Writing policies:      /docs/guides/writing-policies.md
- Simulation guide:      /docs/guides/simulation.md
- ROS2 integration:      /docs/guides/ros2-robot.md
- Custom robot (HTTP):   /docs/guides/custom-robot.md
- LLM agent guard:       /docs/guides/llm-agent.md
- Vendor spec:           /docs/vendor/robot-adapter-spec.md
- DecisionPacket schema: /schemas/DecisionPacket.schema.json
- Examples:              /examples/

В папке _old лежит полностью рабочий код проекта, его нужно переиспользовать

Ecosystem Integration Strategy (Open-Source Growth Model)
Objective

Partenit grows not by marketing, but by ecosystem embedding.

The strategy is to integrate deeply with existing robotics and AI ecosystems
through official, minimal, hardware-agnostic adapters.

We do not build one-off integrations.
We build official adapter modules that implement the same RobotAdapter interface.

This ensures:

Architectural consistency

Zero vendor lock-in

Clean separation between safety logic and transport logic

Organic discoverability inside external communities

Tier 1 Integrations (Core Entry Points)

These adapters must exist and be maintained:

isaac_sim/ — NVIDIA Isaac Sim ecosystem

ros2/ — Generic ROS2 robots

unitree/ — Popular humanoid and quadruped robots

mock/ — Zero-hardware simulation

Each integration:

Implements RobotAdapter

Contains no safety logic

Only translates vendor data → StructuredObservation

Only translates GuardDecision → vendor command format

Remains optional dependency

Does not modify core packages

Tier 2 Integrations (Expansion Layer)

When stable, extend toward:

gazebo/

llm_tool_calling/

open_rmf/

moveit/

These expand Partenit beyond robotics into
LLM agents controlling physical systems.

Architectural Rule

All adapters must implement:

class RobotAdapter(ABC):
    def get_observations(self) -> list[StructuredObservation]
    def send_decision(self, decision: GuardDecision) -> bool
    def get_health(self) -> dict
    def is_simulation(self) -> bool

Adapters:

MUST import types from partenit-core

MUST NOT duplicate schemas

MUST NOT implement policy logic

MUST degrade gracefully if optional dependencies are missing

MUST remain thin translation layers

Safety, risk scoring, and logging live in:

agent-guard

trust-engine

decision-log

Never inside adapters.

Design Philosophy

Adapters are not marketing hooks.

They are:

Infrastructure anchors

Ecosystem bridges

Trust multipliers

The goal is:

Same Partenit code runs in Isaac Sim and on real ROS2 hardware

No code changes between simulation and production

DecisionPacket remains identical across environments

If a scenario produces a GuardDecision in simulation,
it must produce the same GuardDecision on hardware.

Discoverability Strategy

Each official adapter:

Has its own submodule directory

Contains minimal runnable examples

Has a concise README

Is referenced in root README under "Supported Platforms"

We do not create SEO folders.
We create official integrations.

Long-Term Goal

Position Partenit as:

The admissibility and audit standard for physical AI actions.

Ecosystem integrations are entry points into:

NVIDIA robotics

ROS2 community

Humanoid developers

LLM agent engineers

Growth is achieved through:

Technical clarity

Minimal friction

Reproducibility

Auditability

Not through outreach campaigns.

## Claude Code Prompt — Safety Benchmarks + Beautiful Reports (Open Source)

You are Claude Code working inside this Partenit repository.

Goal:
Design + implement a benchmark suite for simulations (first), with a clean path to simulator backends later (Isaac Sim / Gazebo / ROS2). The benchmark suite must produce deterministic results and a beautiful, shareable HTML report. This is open-source only: no enterprise features, no proprietary dependencies.

High-level concept:
We are benchmarking **Action Admissibility & Safety Consistency**, not raw physics accuracy. We want to compare "without guard" vs "with guard" on the same scenario.

Key requirements:
1) Two-level benchmark design:
   - Level 1 (Engine-only): pure Python, deterministic, CPU-only, no external simulators required.
   - Level 2 (Backend): same scenario runner API, but with optional backends (IsaacSimAdapter / ROS2Adapter) added later.

2) Determinism:
   - Every scenario must be reproducible via a fixed seed.
   - Outputs must be stable across runs (same GuardDecisions, same metrics, same report artifacts).

3) Benchmarks to include initially (Level 1):
   - human_crossing_path: human crosses robot trajectory; measure slowdown/stop correctness
   - llm_unsafe_command: unsafe requested speed/zone; measure clamp/block outcomes
   - sensor_degradation: trust drops; measure mode transitions and safety fallback behavior
   - policy_conflict_determinism: two policies conflict; ensure deterministic resolution by priority
   - cross_adapter_determinism (placeholder for now): define the test harness so later we can run same scenario on Mock vs Isaac vs ROS2 and compare outputs.

4) Metrics:
   For each scenario compute:
   - unsafe_acceptance_rate
   - clamp_rate, block_rate
   - time_to_intervention_ms
   - min_human_distance_m (when applicable)
   - collision_count / near_miss_count (define thresholds)
   - risk_curve statistics (stability / spikes)
   - policy_fire_log (timeline of fired rules)
   - decision_log integrity (DecisionPacket/fingerprint verification when available in open stack)

5) Visual report:
   Implement a single command:
     `partenit-bench run <scenario> --with-guard --without-guard --report report.html`
   The HTML report must include:
   - A top-down 2D replay (canvas/SVG) showing robot + humans + trajectories + zones
   - Time series charts: risk, speed, distance-to-human, trust
   - A timeline/event log: policies fired, clamp/block, mode switches
   - A “diff” summary: without vs with guard key deltas
   - A compact “Admissibility Score” per run (define a simple open metric, explain it in report)

6) Repo integration:
   - Implement as part of `partenit-safety-bench` (or create `benchmarks/` under it).
   - Add CLI entrypoint `partenit-bench`.
   - Add `examples/benchmarks/` with minimal configs and a one-line quickstart.
   - Add tests:
       - scenario determinism test (same seed => same outputs)
       - policy conflict determinism test (100% deterministic)
       - report generation smoke test (creates HTML)

7) Constraints:
   - Keep dependencies minimal and open: standard library + existing planned deps for safety-bench (pydantic, numpy, rich). If you need a tiny plotting approach, prefer generating simple inline SVG/Canvas without heavy plotting libs.
   - No Isaac Sim required for Level 1.
   - Keep code structure clean, typed, and well-documented.
   - Do not change core data contracts in a breaking way.

Deliverables:
- Directory structure and new modules
- Scenario YAML/JSON format spec (small, clear)
- CLI implementation
- HTML report generator
- 3–5 built-in scenarios + expected outputs
- Tests proving determinism and correctness

You have freedom to choose the best implementation details as long as the above requirements are satisfied.