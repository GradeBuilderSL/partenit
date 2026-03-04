[<img src="../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# LLM Agent Guard

This guide shows how to insert `partenit-agent-guard` between an LLM with tool-calling
and environment-affecting actions, so every proposed action is validated before execution.

---

## The problem

LLMs propose actions. They cannot guarantee those actions are safe.

```
LLM: "navigate_to(zone='shipping', speed=3.0)"   ← unsafe near a human
         ↓  no check
    Robot executes at full speed
```

## The solution

```
LLM: "navigate_to(zone='shipping', speed=3.0)"
         ↓
    AgentGuard.check_action(...)
         ↓  evaluates safety policies
    Decision: MODIFIED → speed clamped to 0.3 m/s
         ↓
    DecisionLogger.create_packet(...)  ← tamper-evident audit
         ↓
    Robot executes safely
```

---

## Quick integration

```python
from partenit.agent_guard import AgentGuard
from partenit.decision_log import DecisionLogger

guard = AgentGuard()
guard.load_policies("./policies/warehouse.yaml")
log = DecisionLogger()

def guarded_tool_call(tool_name: str, tool_input: dict, context: dict) -> dict:
    """Intercept every LLM tool call before execution."""
    decision = guard.check_action(
        action=tool_name,
        params=tool_input,
        context=context,
    )

    packet = log.create_packet(
        action_requested=tool_name,
        action_params=tool_input,
        guard_decision=decision,
    )

    if decision.allowed:
        # Use modified_params if guard clamped any values
        safe_params = decision.modified_params or tool_input
        return {"status": "execute", "params": safe_params}
    else:
        return {"status": "blocked", "reason": decision.rejection_reason}
```

---

## Using with the Anthropic SDK

The `examples/llm_agent_guard_demo.py` shows a full working example.
Here is the core pattern:

```python
import anthropic
from partenit.agent_guard import AgentGuard

guard = AgentGuard()
guard.load_policies("./policies/warehouse.yaml")
client = anthropic.Anthropic()

# 1. Define tools the LLM can call
tools = [
    {
        "name": "navigate_to",
        "description": "Move the robot to a zone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "zone": {"type": "string"},
                "speed": {"type": "number"},
            },
            "required": ["zone", "speed"],
        },
    }
]

# 2. Get tool calls from the LLM
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "Deliver pallet to shipping zone quickly."}],
)

# 3. Guard every tool call before executing
for block in response.content:
    if block.type == "tool_use":
        context = {"human": {"distance": 1.2}}   # from your sensors
        decision = guard.check_action(
            action=block.name,
            params=block.input,
            context=context,
        )
        if decision.allowed:
            effective = decision.modified_params or block.input
            print(f"Executing {block.name} with {effective}")
        else:
            print(f"Blocked: {decision.rejection_reason}")
```

Run the full demo:

```bash
python examples/llm_agent_guard_demo.py

# With real Claude (requires ANTHROPIC_API_KEY):
python examples/llm_agent_guard_demo.py --real-llm
```

---

## Context: how to populate it

The `context` dict feeds the policy condition evaluator.
Build it from your sensor observations:

```python
from partenit.adapters import MockRobotAdapter

adapter = MockRobotAdapter()
observations = adapter.get_observations()

context: dict = {}
for obs in observations:
    if obs.treat_as_human:
        d = obs.distance()
        existing = context.get("human", {})
        if not existing or d < existing.get("distance", float("inf")):
            context["human"] = {"distance": d, "object_id": obs.object_id}
```

Add any domain metrics your policies reference:

```python
context["speed"] = current_speed          # for speed policies
context["zone_type"] = current_zone_type  # for zone policies
context["trust"] = sensor_trust_value     # for trust-aware policies
```

---

## Handling blocked actions

When the guard blocks an action, the LLM can be informed and asked to try again:

```python
if not decision.allowed:
    # Feed the rejection back to the LLM
    messages.append({
        "role": "user",
        "content": (
            f"The action {tool_name} was blocked by the safety system. "
            f"Reason: {decision.rejection_reason}. "
            f"Risk score: {decision.risk_score.value:.2f}. "
            "Please suggest a safe alternative."
        ),
    })
    # Continue the conversation...
```

---

## Deployment modes

Partenit supports three deployment modes that change guard behavior
without restarting your agent:

| Mode | Guard behavior |
|---|---|
| `shadow` | Guard runs, logs everything, does not block. Use for baseline. |
| `advisory` | Hard constraint violations are blocked; others are logged only. |
| `full` | Guard enforces all policies. Production mode. |

Switch at runtime:

```bash
curl -X POST http://localhost:8000/mode -d '{"mode": "advisory"}'
```

---

## What to log

Always log **both** allowed and blocked decisions:

```python
# In your agent loop — log EVERY decision, not just blocks
packet = log.create_packet(
    action_requested=tool_name,
    action_params=tool_input,
    guard_decision=decision,
    mission_goal=current_mission_description,
)
```

This is required for:
- Incident investigation ("why did the robot stop?")
- Compliance audits
- Training data for policy improvement
- Verifying that the guard was never bypassed
