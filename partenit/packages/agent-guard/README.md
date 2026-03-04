[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

## partenit-agent-guard

**Purpose:** safety middleware that intercepts actions (LLM tool calls, ROS skills, generic function calls) and decides whether to allow, block, or modify them.

Core ideas:
- Every action passes through the guard with its parameters and context.
- Policies from `partenit-policy-dsl` and trust signals from `partenit-trust-engine` are evaluated.
- A `GuardDecision` is produced, along with a `RiskScore` and applied policies.

Planned components:
- `AgentGuard` class with `check_action(...) -> GuardDecision`.
- Decorators for guarding Python functions (`@guard.protect(...)`).
- Adapters for LLM tool-calls, ROS2-like skills, and generic call interfaces.
- Optional integration with `partenit-decision-log` to log every decision.

Implementation details and APIs are outlined in `IMPLEMENTATION_PLAN.md`.

[<img src="../../../partenit_robot.png" alt="Partenit robot" width="320" />](https://partenit.io)

Made with love for the future at [Partenit](https://partenit.io).

