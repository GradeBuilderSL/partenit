[<img src="../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# ROS2 Robot Integration Guide

This guide covers how to connect a ROS2-based robot to Partenit using
`ROS2Adapter` from `partenit-adapters`.

---

## Prerequisites

- ROS2 Humble (or later) installed and sourced
- `rclpy` available in the Python environment
- `partenit-adapters` installed

```bash
# Source your ROS2 installation
source /opt/ros/humble/setup.bash

# Install Partenit packages
pip install partenit-core partenit-agent-guard partenit-adapters partenit-decision-log
```

---

## Quick Start

```python
from partenit.adapters.ros2 import ROS2Adapter
from partenit.agent_guard import AgentGuard
from partenit.decision_log import DecisionLogger

# Create adapter — this initializes a rclpy node named "partenit_guard"
adapter = ROS2Adapter(node_name="partenit_guard")

guard = AgentGuard()
guard.load_policies("./policies/warehouse.yaml")

log = DecisionLogger(storage_dir="./decisions/")

# Get observations from ROS2 topic /partenit/observations
observations = adapter.get_observations()

# Build context and evaluate
context: dict = {}
for obs in observations:
    if obs.treat_as_human:
        d = obs.distance()
        existing = context.get("human", {})
        if not existing or d < existing.get("distance", float("inf")):
            context["human"] = {"distance": d, "object_id": obs.object_id}

decision = guard.check_action(
    action="navigate_to",
    params={"zone": "shipping", "speed": 1.5},
    context=context,
    observations=observations,
)

if decision.allowed:
    effective = decision.modified_params or {"zone": "shipping", "speed": 1.5}
    # Publish decision to /partenit/command
    adapter.send_decision(decision)
else:
    print(f"Blocked: {decision.rejection_reason}")

log.create_packet(
    action_requested="navigate_to",
    action_params={"zone": "shipping", "speed": 1.5},
    guard_decision=decision,
)

# Clean up
adapter.destroy()
```

---

## ROS2 Topics

`ROS2Adapter` uses these ROS2 topics:

| Direction | Topic | Message type |
|---|---|---|
| Subscribe | `/partenit/observations` | `partenit_msgs/ObservationArray` |
| Publish | `/partenit/command` | `partenit_msgs/GuardDecision` |

The `partenit_msgs` package is part of the enterprise distribution.
For the open-source version, use `HTTPRobotAdapter` or implement
your own bridge that publishes `StructuredObservation` objects.

---

## StructuredObservation Mapping

Your perception node must produce `StructuredObservation` objects.
These are the canonical type defined in `partenit-core`:

```python
from partenit.core.models import StructuredObservation

obs = StructuredObservation(
    object_id="person-42",
    class_best="human",
    class_set=["human", "worker"],   # 'human' in set → treat_as_human=True (auto)
    position_3d=(1.2, 0.0, 0.0),     # (x, y, z) in meters, robot-centric
    velocity=(0.1, 0.0, 0.0),        # (vx, vy, vz) in m/s
    confidence=0.93,
    sensor_trust=0.95,
    depth_variance=0.02,
    source_id="camera_front",
)
```

Key fields:

| Field | Description |
|---|---|
| `class_set` | If `"human"` is in this list, `treat_as_human` is set to `True` automatically |
| `position_3d` | Robot-centric frame, z=0 for floor-level detection |
| `sensor_trust` | From your `SensorTrustModel` (0.0–1.0) |
| `location_uncertain` | Set to `True` when confidence has decayed below 0.1 |
| `frame_hash` | SHA256 of raw sensor frame for audit trail (optional but recommended) |

---

## Same Code, Different Adapters

The adapter pattern ensures your guard logic does not change when switching
between simulation and real robot:

```python
import os

if os.environ.get("ROBOT_MODE") == "ros2":
    from partenit.adapters.ros2 import ROS2Adapter
    adapter = ROS2Adapter(node_name="partenit_guard")
elif os.environ.get("ROBOT_MODE") == "http":
    from partenit.adapters.http import HTTPRobotAdapter
    adapter = HTTPRobotAdapter(base_url="http://192.168.1.100")
else:
    from partenit.adapters import MockRobotAdapter
    adapter = MockRobotAdapter()

# Everything below is identical regardless of adapter
obs = adapter.get_observations()
decision = guard.check_action(action="navigate_to", params={...}, context={...})
adapter.send_decision(decision)
```

---

## Health Check

```python
health = adapter.get_health()
print(health)
# {'status': 'ok', 'robot_id': 'partenit_guard', 'timestamp': '2025-...'}
```

Use this to verify connectivity before starting a mission.

---

## Lifecycle

ROS2 resources must be released when your guard node shuts down:

```python
try:
    # Your guard loop here
    while True:
        obs = adapter.get_observations()
        # ...
finally:
    adapter.destroy()  # Destroys the rclpy node and calls rclpy.shutdown()
```

---

## Limitations (Open Source)

The open-source `ROS2Adapter` provides the integration scaffolding.
Full production features (message bridging, QoS profiles, multi-robot
coordination, `partenit_msgs` definitions) are in the enterprise
distribution.

For now, you can:
- Use the open-source adapter with your own message bridge
- Use `HTTPRobotAdapter` if your ROS2 robot exposes an HTTP API
- Use `MockRobotAdapter` for development and testing

---

## What to Read Next

- [Simulation guide](simulation.md) — test without hardware
- [Custom robot (HTTP)](custom-robot.md) — vendor HTTP integration
- [Writing policies](writing-policies.md) — define safety rules
