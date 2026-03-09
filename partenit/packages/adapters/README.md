[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# partenit-adapters

> **One guard, any robot. Swap the adapter, keep everything else.**

`partenit-adapters` connects Partenit to your robot or simulator.
Every adapter implements the same `RobotAdapter` interface —
the guard, policies, and decision log never change regardless of which adapter you use.

```bash
pip install partenit-adapters           # Mock + HTTP
pip install "partenit-adapters[http]"   # + httpx for HTTP robots
pip install "partenit-adapters[ros2]"   # + ROS2 support (requires rclpy)
```

---

## The interface

All adapters implement:

```python
class RobotAdapter(ABC):
    def get_observations(self) -> list[StructuredObservation]: ...
    def send_decision(self, decision: GuardDecision) -> bool: ...
    def get_health(self) -> dict: ...
    def is_simulation(self) -> bool: ...
```

Adapters are **thin translation layers** only:
- Translate vendor sensor data → `StructuredObservation`
- Translate `GuardDecision` → vendor command format
- Zero safety logic inside adapters

---

## Adapters

### `MockRobotAdapter` — no hardware needed

```python
from partenit.adapters import MockRobotAdapter

adapter = MockRobotAdapter()
adapter.add_human("worker-1", x=1.2, y=0.0)   # place humans in the scene
adapter.set_robot_speed(1.5)

obs = adapter.get_observations()
# [StructuredObservation(object_id='worker-1', class_name='human', distance_m=1.2, ...)]
```

Used by `GuardedRobot` and all safety-bench scenarios. No external dependencies.

---

### `HTTPRobotAdapter` — any REST robot

```python
from partenit.adapters.http import HTTPRobotAdapter

adapter = HTTPRobotAdapter(base_url="http://192.168.1.100")
```

The robot must expose:

```
GET  /partenit/observations  →  StructuredObservation[]
POST /partenit/command       ←  GuardDecision
GET  /partenit/health        →  {status, robot_id, timestamp}
```

OpenAPI spec: [schemas/robot-adapter-api.yaml](../../../schemas/robot-adapter-api.yaml)

Built-in circuit breaker: after 5 consecutive failures, adapter stops sending commands
and raises `HTTPRobotUnavailable` until the robot recovers.

---

### `ROS2Adapter` — ROS2 robots

```python
from partenit.adapters.ros2 import ROS2Adapter

adapter = ROS2Adapter(node_name="partenit_guard")
```

Subscribes to standard ROS2 topics for observations.
Graceful `ImportError` if `rclpy` is not installed — won't break non-ROS environments.

---

### `IsaacSimAdapter` — NVIDIA Isaac Sim

```python
from partenit.adapters.isaac_sim import IsaacSimAdapter

adapter = IsaacSimAdapter(
    base_url="http://localhost:8000",
    robot_id="h1-sim",
)
```

Connects to an Isaac Sim bridge over HTTP (same contract as `HTTPRobotAdapter`).
See [examples/isaac_sim/](../../../examples/isaac_sim/) for the bridge script.

Omniverse Extension template: [adapters/isaac_sim_extension/](src/partenit/adapters/isaac_sim_extension/)

---

### `UnitreeAdapter` — Unitree robots (H1, G1, B2)

```python
from partenit.adapters.unitree import UnitreeAdapter

adapter = UnitreeAdapter(node_name="partenit_unitree")
```

Extends `ROS2Adapter` with Unitree-specific topic names and observation mapping.
Requires `rclpy` and Unitree ROS2 SDK.

---

### `GazeboAdapter` — Gazebo simulator

```python
from partenit.adapters.gazebo import GazeboAdapter

adapter = GazeboAdapter(base_url="http://localhost:9000")
```

HTTP bridge adapter for Gazebo. Same contract as `HTTPRobotAdapter`.

---

### `LLMToolCallGuard` — wrap LLM tool calls

```python
from partenit.adapters.llm_tool_calling import LLMToolCallGuard

guard_wrapper = LLMToolCallGuard(
    guard=agent_guard,
    whitelist=["navigate_to", "pick_up", "place"],
)

# Before executing any LLM tool call:
result = guard_wrapper.check_tool_call(
    tool_name="navigate_to",
    arguments={"zone": "shipping", "speed": 3.0},
    context={"human": {"distance": 0.9}},
)

if result.allowed:
    execute_tool(result.modified_params or result.arguments)
else:
    return f"Blocked: {result.rejection_reason}"
```

`LLMToolCallGuard` is NOT a `RobotAdapter` — it wraps any LLM orchestration layer.
Use it to guard Claude tool calls, OpenAI function calls, or any callable.

---

### Stubs (planned)

| Adapter | Status | Notes |
|---|---|---|
| `OpenRMFAdapter` | Stub — `NotImplementedError` | Use HTTP for now |
| `MoveItAdapter` | Stub — `NotImplementedError` | Use ROS2 for now |

---

## Swap the adapter, keep everything else

```python
# Development / CI
adapter = MockRobotAdapter()
adapter.add_human("h1", x=1.2, y=0.0)

# Real ROS2 robot — only this line changes
adapter = ROS2Adapter(node_name="partenit_guard")

# Isaac Sim
adapter = IsaacSimAdapter(base_url="http://localhost:8000")

# Any vendor with HTTP API
adapter = HTTPRobotAdapter(base_url="http://192.168.1.100")

# Everything below is identical
from partenit.agent_guard import GuardedRobot

robot = GuardedRobot(adapter, policy_path="policies/warehouse.yaml")
decision = robot.navigate_to(zone="shipping", speed=2.0)
```

Same policies. Same decisions. Same audit log.
Whether you test in CI with `MockRobotAdapter` or deploy with `ROS2Adapter`,
the `GuardDecision` and `DecisionPacket` are identical.

---

## HTTP vendor contract

If you are integrating a new robot, implement these three endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/partenit/observations` | `GET` | Return current sensor data as `StructuredObservation[]` |
| `/partenit/command` | `POST` | Receive and execute a `GuardDecision` |
| `/partenit/health` | `GET` | Return `{status, robot_id, timestamp}` |

Full spec: [schemas/robot-adapter-api.yaml](../../../schemas/robot-adapter-api.yaml)
Guide: [docs/guides/custom-robot.md](../../../docs/guides/custom-robot.md)

---

## Dependencies

```
pydantic >= 2.0
partenit-core >= 0.1.0
httpx >= 0.24          # for HTTPRobotAdapter (optional extra)
rclpy                  # for ROS2Adapter (optional, graceful import)
```

---

[Documentation](../../../docs/guides/custom-robot.md) · [Examples](../../../examples/) · [Issues](https://github.com/GradeBuilderSL/partenit/issues)
