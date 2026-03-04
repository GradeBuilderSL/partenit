[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

## partenit-adapters

**Purpose:** hardware- and simulator-agnostic adapters that connect robots to the Partenit guard and engines.

Key concept:
- All robot-specific integration lives here.
- Core packages (`core`, `policy-dsl`, `trust-engine`, `agent-guard`, `decision-log`, `safety-bench`) remain unaware of the underlying robot platform.

Planned components:
- `RobotAdapter` abstract base class with:
  - `get_observations() -> list[StructuredObservation]`
  - `send_decision(decision: GuardDecision) -> bool`
  - `get_health() -> dict`
  - `is_simulation() -> bool`
- `MockRobotAdapter` — wraps the mock world and robot from `partenit-safety-bench`.
- `HTTPRobotAdapter` — REST-based adapter for any robot exposing:
  - `GET  /partenit/observations`
  - `POST /partenit/command`
  - `GET  /partenit/health`
- `ROS2Adapter` — optional adapter for ROS2 robots (graceful ImportError if `rclpy` is missing).
- `IsaacSimAdapter` — simulation adapter that wraps `HTTPRobotAdapter` to connect to an
  Isaac Sim HTTP gateway implementing the standard Partenit robot API.

The vendor HTTP contract will be specified in:
- `schemas/robot-adapter-api.yaml`
- `docs/vendor/robot-adapter-spec.md`

### Isaac Sim usage (HTTP bridge mode)

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

[<img src="../../../partenit_robot.png" alt="Partenit robot" width="320" />](https://partenit.io)

Made with love for the future at [Partenit](https://partenit.io).

