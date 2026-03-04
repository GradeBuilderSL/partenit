[<img src="partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![Tests](https://img.shields.io/badge/tests-175%20passing-brightgreen)
![Packages](https://img.shields.io/badge/packages-7%20open--source-blue)

Partenit — open-source safety and cognitive control infrastructure for physical AI agents (robots, LLM agents, autonomous systems).

## Overview

Partenit provides a hardware-agnostic safety and audit layer that sits between:
- high-level planners (missions, LLM agents, task planners)
- low-level controllers (ROS, motor controllers, vendor APIs)

This repository contains the **open ecosystem**: shared types, policy DSL, trust models, safety sandbox, decision logging, adapters, and a local analyzer UI.
Enterprise features (cloud, formal verification, conformal prediction, compliance exports, etc.) are intentionally kept closed and are only referenced here.

## Repository layout

- **`partenit/packages/`** — Python packages installable via `pip`:
  - `core` — shared types, contracts, base classes
  - `policy-dsl` — YAML policy language + parser/validator
  - `trust-engine` — sensor and object trust models
  - `agent-guard` — action/LLM tool-call safety middleware
  - `safety-bench` — simulation sandbox and scenarios
  - `decision-log` — DecisionPacket format + reference impl
  - `adapters` — hardware/simulator adapters (Mock, HTTP, ROS2)
- **`analyzer/`** — local web UI (FastAPI backend + React frontend)
- **`schemas/`** — JSON Schemas and OpenAPI contracts
- **`docs/`** — getting started, guides, and reference docs
- **`examples/`** — small runnable examples and demos
- **`tests/`** — cross-package and integration tests

## Quick mental model

- **Core**: defines the open standard types (`StructuredObservation`, `PolicyRule`, `DecisionPacket`, `DecisionFingerprint`, etc.).
- **Engines**: policy DSL, trust engine, agent guard, safety bench, decision log.
- **Adapters**: bridge between any robot/simulator and the Partenit core types.
- **Analyzer**: visual interface for decisions, trust state, and scenarios.

All robot- and simulator-specific code lives in `partenit/packages/adapters` or in example projects. Core packages stay hardware-agnostic.

## Supported platforms

Partenit works across simulation and real hardware via adapters:

- **Mock simulation** — `MockRobotAdapter` + `partenit-safety-bench` (no hardware required).
- **HTTP robots** — any robot exposing the Partenit HTTP API
  (`/partenit/observations`, `/partenit/command`, `/partenit/health`).
- **ROS2 robots** — `ROS2Adapter` (optional `rclpy` dependency).
- **Isaac Sim** — `IsaacSimAdapter` wrapping an Isaac HTTP gateway.
- **Unitree (ROS2)** — `UnitreeAdapter` as a thin wrapper over `ROS2Adapter`.
- **Gazebo** — `GazeboAdapter` via HTTP gateway.
- **LLM tool calls** — `LLMToolCallGuard` wraps any LLM tool-calling layer.

The guard and policies are identical across all of these — only the adapter changes.

### Adapter swap example

```python
import os
from pathlib import Path

from partenit.agent_guard import AgentGuard

mode = os.environ.get("PARTENIT_ADAPTER", "mock")

if mode == "ros2":
    from partenit.adapters.ros2 import ROS2Adapter
    adapter = ROS2Adapter(node_name="partenit_guard")
elif mode == "http":
    from partenit.adapters import HTTPRobotAdapter
    adapter = HTTPRobotAdapter(base_url="http://robot.local:8080")
elif mode == "isaac":
    from partenit.adapters.isaac_sim import IsaacSimAdapter
    adapter = IsaacSimAdapter(base_url="http://localhost:7000")
else:
    from partenit.adapters import MockRobotAdapter
    adapter = MockRobotAdapter()

guard = AgentGuard()
guard.load_policies(Path("examples/warehouse/policies.yaml"))

observations = adapter.get_observations()
decision = guard.check_action(
    action="navigate_to",
    params={"zone": "shipping", "speed": 1.8},
    context={},
    observations=observations,
)
adapter.send_decision(decision)
```

## Quick start

```bash
pip install partenit-core partenit-agent-guard partenit-safety-bench
```

```python
from pathlib import Path
from partenit.adapters import MockRobotAdapter
from partenit.agent_guard import AgentGuard

adapter = MockRobotAdapter()
guard = AgentGuard()
guard.load_policies(Path("examples/warehouse/policies.yaml"))

obs = adapter.get_observations()
decision = guard.check_action(
    action="navigate_to",
    params={"zone": "shipping", "speed": 1.5},
    context={},
    observations=obs,
)
print(decision.allowed)           # True or False
print(decision.modified_params)   # speed may be clamped
print(decision.risk_score.value)  # 0.0 – 1.0
```

### Safety benchmarks

Run a built-in safety scenario and get a visual HTML report:

```bash
# Single scenario — with and without guard, full HTML report
partenit-bench run examples/benchmarks/human_crossing_path.yaml \
    --with-guard --without-guard \
    --report report.html

# Run all scenarios at once
partenit-bench run-all examples/benchmarks/ --report report.html
```

Open `report.html` in any browser. No server required.

Available built-in scenarios:
- `human_crossing_path` — worker crosses robot trajectory
- `blind_spot` — human in low-confidence detection zone
- `llm_unsafe_command` — LLM requests unsafe speed near a human
- `sensor_degradation` — trust degrades mid-mission; conservative fallback
- `policy_conflict_determinism` — priority-based conflict resolution (100% deterministic)
- `cross_adapter_determinism` — same scenario reproducible across adapter swap

See [docs/guides/benchmarks.md](docs/guides/benchmarks.md) for the full guide.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, architecture rules,
and the pull request process.

## Open vs Enterprise

- **Open in this repository**:
  - Policy DSL + basic policy engine
  - Basic risk scoring (distance + velocity + trust)
  - Mock/HTTP/ROS2 adapters
  - Safety bench + built-in scenarios
  - Decision log + fingerprint verification
  - Analyzer web UI
  - JSON Schemas for `DecisionPacket` and `DecisionFingerprint`
  - Documentation and examples

- **Enterprise (closed, not in this repo)**:
  - Conformal prediction with coverage guarantees
  - Plan-conditional risk scoring
  - GraphRAG policy retrieval
  - Formal verification (CBF/STL)
  - Fleet coordination and policy broadcast
  - Cloud sync and managed storage
  - Compliance export tooling
  - Policy authoring UI
  - Hardware licensing binding

## Contributing

This project is designed as a modular ecosystem. Each package under `partenit/packages/`:
- is installable on its own
- has its own `pyproject.toml` and `README.md`
- exposes a small, well-typed Python API

See `IMPLEMENTATION_PLAN.md` and `docs/` for contribution guidelines once initial scaffolding is in place.

[<img src="partenit_robot.png" alt="Partenit robot" width="320" />](https://partenit.io)

Made with love for the future at [Partenit](https://partenit.io).

