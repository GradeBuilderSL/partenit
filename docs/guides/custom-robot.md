[<img src="../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# Custom Robot (HTTP) Integration Guide

This guide is for robot vendors and integrators who do not use ROS2.
If your robot controller (or a gateway next to it) can expose a simple HTTP API,
`HTTPRobotAdapter` can connect it to Partenit with no changes to the core packages.

---

## The HTTP Contract

Your robot MUST implement exactly these three endpoints:

| Method | Path | Description |
|---|---|---|
| `GET` | `/partenit/observations` | Return current sensor observations |
| `POST` | `/partenit/command` | Accept and execute a GuardDecision |
| `GET` | `/partenit/health` | Report robot health status |

The full machine-readable OpenAPI spec is at `schemas/robot-adapter-api.yaml`.
The human-readable spec is at `docs/vendor/robot-adapter-spec.md`.

---

## Using HTTPRobotAdapter

```python
from partenit.adapters.http import HTTPRobotAdapter
from partenit.agent_guard import AgentGuard
from partenit.decision_log import DecisionLogger

# Connect to your robot
adapter = HTTPRobotAdapter(
    base_url="http://192.168.1.100",
    timeout=2.0,
    headers={"Authorization": "Bearer YOUR_TOKEN"},  # optional
)

guard = AgentGuard()
guard.load_policies("./policies/warehouse.yaml")
log = DecisionLogger(storage_dir="./decisions/")

# Get observations from the robot
observations = adapter.get_observations()

# Build context
context: dict = {}
for obs in observations:
    if obs.treat_as_human:
        d = obs.distance()
        existing = context.get("human", {})
        if not existing or d < existing.get("distance", float("inf")):
            context["human"] = {"distance": d, "object_id": obs.object_id}

# Evaluate with guard
decision = guard.check_action(
    action="navigate_to",
    params={"zone": "shipping", "speed": 1.5},
    context=context,
    observations=observations,
)

# Log (always, even on block)
log.create_packet(
    action_requested="navigate_to",
    action_params={"zone": "shipping", "speed": 1.5},
    guard_decision=decision,
)

# Send to robot (only if allowed)
if decision.allowed:
    adapter.send_decision(decision)
else:
    print(f"Blocked: {decision.rejection_reason}")

adapter.close()
```

---

## GET /partenit/observations

Your endpoint must return a JSON array of objects that match `StructuredObservation`:

```json
[
  {
    "object_id": "worker-1",
    "class_best": "human",
    "class_set": ["human"],
    "position_3d": [1.2, 0.0, 0.0],
    "velocity": [0.0, -0.3, 0.0],
    "confidence": 0.93,
    "depth_variance": 0.02,
    "sensor_trust": 0.95,
    "timestamp": "2025-01-01T12:00:00Z",
    "frame_hash": "e3b0c44...",
    "source_id": "camera_front"
  }
]
```

Key rules:

- `position_3d` — robot-centric frame, in meters. `[x, y, z]` where x=forward.
- `class_set` — include `"human"` if there is any possibility the object is human.
  Partenit automatically sets `treat_as_human=True` when `"human"` is in this list.
- `frame_hash` — SHA256 of the raw sensor frame. Optional but strongly recommended for audit.
- Return an empty array `[]` if nothing is detected — do not return a 404.

---

## POST /partenit/command

Partenit sends a `GuardDecision` JSON object. Your robot must:
- Execute the action described by `modified_params` when `allowed=true`.
- Refuse to execute the original unsafe action when `allowed=false`.
- Optionally surface `rejection_reason` and `applied_policies` to operators.

```json
{
  "allowed": true,
  "modified_params": {"zone": "shipping", "speed": 0.3},
  "rejection_reason": null,
  "risk_score": {
    "value": 0.64,
    "contributors": {"distance": 0.88, "speed": 0.67, "trust": 0.0}
  },
  "applied_policies": ["human_proximity_slowdown"],
  "suggested_alternative": null,
  "latency_ms": 2.1
}
```

Respond with `200 OK` and `{"status": "ok"}` on success.

---

## GET /partenit/health

```json
{
  "status": "ok",
  "robot_id": "my-robot-001",
  "timestamp": "2025-01-01T12:00:00Z"
}
```

- `status`: `"ok"` | `"degraded"` | `"e_stop"`
- `robot_id`: stable identifier for this robot instance

---

## Example Implementation (Python FastAPI)

A minimal server-side implementation on the robot:

```python
from fastapi import FastAPI
from partenit.core.models import GuardDecision, StructuredObservation
from datetime import datetime, timezone

app = FastAPI()

# Replace with your real robot sensor interface
def get_sensor_data() -> list[dict]:
    return [...]

# Replace with your real robot command interface
def execute_command(params: dict) -> None:
    pass


@app.get("/partenit/observations")
def observations():
    raw = get_sensor_data()
    return raw   # must match StructuredObservation schema


@app.post("/partenit/command")
def command(decision: GuardDecision):
    if decision.allowed:
        params = decision.modified_params or {}
        execute_command(params)
    return {"status": "ok"}


@app.get("/partenit/health")
def health():
    return {
        "status": "ok",
        "robot_id": "my-robot-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
```

---

## Testing Your Integration

```python
from partenit.adapters.http import HTTPRobotAdapter

adapter = HTTPRobotAdapter(base_url="http://192.168.1.100")

# 1) Health check
health = adapter.get_health()
print(health)  # {'status': 'ok', 'robot_id': '...', 'timestamp': '...'}

# 2) Get observations
obs = adapter.get_observations()
print(f"{len(obs)} objects detected")

# 3) Run a safety bench scenario against real hardware
from partenit.safety_bench import ScenarioRunner
runner = ScenarioRunner()
config = runner.load("examples/warehouse/human_crossing.yaml")
result = runner.run(config, with_guard=True)
print(result.summary())
```

---

## Context: Same Code, Different Adapter

The only change between simulation and real hardware is the adapter.
All guard logic, policies, and decision logging remain identical:

```python
import os

if os.environ.get("ROBOT_MODE") == "production":
    adapter = HTTPRobotAdapter(base_url="http://192.168.1.100")
else:
    from partenit.adapters import MockRobotAdapter
    adapter = MockRobotAdapter()

# Everything below is identical in both modes
obs = adapter.get_observations()
decision = guard.check_action(action="navigate_to", params={...}, context={...})
adapter.send_decision(decision)
```

---

## What to Read Next

- [Vendor specification](../vendor/robot-adapter-spec.md) — full HTTP contract
- [Simulation guide](simulation.md) — test without hardware
- [Writing policies](writing-policies.md) — define safety rules
