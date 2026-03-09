[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# partenit-agent-guard

> **Every action your robot takes — validated first.**

`partenit-agent-guard` is the safety middleware that sits between your controller
and your robot. It intercepts every action, evaluates it against your safety policies,
and returns a `GuardDecision`: allow, block, or modify with clamped parameters.

```bash
pip install partenit-agent-guard
```

---

## Quickstart — GuardedRobot (1-line integration)

```python
from partenit.adapters import MockRobotAdapter
from partenit.agent_guard import GuardedRobot

robot = GuardedRobot(
    MockRobotAdapter(),
    policy_path="examples/warehouse/policies.yaml",
    session_name="warehouse_run",
)

decision = robot.navigate_to(zone="shipping", speed=2.0)

print(decision.allowed)           # True / False
print(decision.risk_score.value)  # 0.0 – 1.0
print(decision.applied_policies)  # which rules fired
```

`GuardedRobot` combines adapter + guard + decision logger in one object.
The adapter is duck-typed — works with `MockRobotAdapter`, `HTTPRobotAdapter`,
`ROS2Adapter`, or any object with `get_observations()` / `send_decision()`.

### GuardedRobot API

```python
robot = GuardedRobot(
    adapter,                          # any robot adapter
    policy_path="policies/",          # YAML policies (file or directory)
    session_name="my_session",        # enables decision recording
    risk_threshold=0.8,               # block threshold (default: 0.8)
)

robot.navigate_to(zone="A2", speed=1.5)  # guard checks speed + proximity
robot.pick_up(target="box_01")           # guard validates safety constraints
robot.move_to(x=5.0, y=3.0, speed=1.0)  # guard may clamp speed
robot.stop()                             # emergency stop, bypasses guard

decision = robot.execute_action("custom_action", param1=val1, param2=val2)

robot.last_decision   # most recent GuardDecision
robot.risk_score      # float 0.0–1.0 from last decision
robot.events          # list of SafetyEvents from this session
robot.session_name    # session label
```

---

## Low-level API — AgentGuard

For full control over each decision step:

```python
from partenit.agent_guard import AgentGuard

guard = AgentGuard(risk_threshold=0.8)
guard.load_policies("./policies/warehouse.yaml")

result = guard.check_action(
    action="navigate_to",
    params={"zone": "A3", "speed": 2.0},
    context={"human": {"distance": 1.2}},
)

if result.allowed:
    execute(result.modified_params)  # speed may be clamped to 0.3
else:
    print(result.rejection_reason)  # "emergency_stop"
```

### GuardDecision fields

| Field | Type | Description |
|---|---|---|
| `allowed` | `bool` | Whether action is permitted |
| `modified_params` | `dict \| None` | Safe parameters (e.g. clamped speed) |
| `rejection_reason` | `str \| None` | Policy rule that blocked the action |
| `risk_score` | `RiskScore` | Score 0–1 with feature attribution |
| `applied_policies` | `list[str]` | All rules that fired |
| `suggested_alternative` | `dict \| None` | Alternative safe action |

---

## Decorator — guard any Python function

```python
from partenit.agent_guard import AgentGuard, guard_action

guard = AgentGuard()
guard.load_policies("./policies/")

@guard_action(guard, action_name="navigate_to", context_key="world_state")
def navigate_to(zone: str, speed: float, world_state: dict) -> bool:
    # Only executed if guard allows
    return robot.send_command(zone, speed)

# Call normally — guard check happens automatically
navigate_to(zone="A3", speed=2.0, world_state={"human": {"distance": 1.2}})
```

---

## ROS2SkillGuard — guard ROS2 action goals

```python
from partenit.agent_guard import AgentGuard, ROS2SkillGuard

guard = AgentGuard()
guard.load_policies("./policies/")

ros2_guard = ROS2SkillGuard(guard)

# Before sending a goal to NavigateToPose:
goal = {"pose": {"x": 5.0, "y": 0.0}, "speed": 2.5}
context = {"human": {"distance": 1.2}}

decision = ros2_guard.check_goal("navigate_to_pose", goal, context)
if decision.allowed:
    action_client.send_goal(decision.modified_params or goal)
else:
    logger.warning("Blocked: %s", decision.rejection_reason)
```

`ROS2SkillGuard` has zero dependency on `rclpy` — the caller converts ROS2
message objects to plain dicts before passing them.

---

## How it works

```
Your controller / LLM planner
           ↓
      GuardedRobot                 ← 1-line integration
  ┌────────────────────────────┐
  │  get_observations(adapter) │   ← current sensor state
  │  check_action(guard)       │   ← evaluate policies + risk
  │  send_decision(adapter)    │   ← allowed or stop
  │  create_packet(logger)     │   ← audit record (always)
  └────────────────────────────┘
           ↓
      RobotAdapter
  (Mock / HTTP / ROS2 / Isaac Sim)
           ↓
        Robot
```

Every decision is logged as a `DecisionPacket` with a SHA-256 fingerprint.
Even blocked actions are logged — the audit trail is complete.

---

## Integration with decision-log

When `partenit-decision-log` is installed and `session_name` is provided,
every decision is automatically recorded to `decisions/<session_name>/`.

```bash
# Explain why the robot stopped
partenit-why decisions/warehouse_run/

# Watch live decisions
partenit-watch decisions/

# Replay the full session
partenit-log replay decisions/warehouse_run/
```

---

## Policy YAML example

```yaml
rule_id: human_proximity_slowdown
name: "Human Proximity Speed Limit"
priority: safety_critical
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
```

More: [Writing Policies](../../../docs/guides/writing-policies.md) ·
[Policy DSL](../policy-dsl/)

---

[Documentation](../../../docs/) · [Examples](../../../examples/) · [Issues](https://github.com/GradeBuilderSL/partenit/issues)
