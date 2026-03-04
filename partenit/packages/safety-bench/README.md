[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

## partenit-safety-bench

**Purpose:** simulation sandbox and scenario runner for testing safety behavior without real hardware.

This package will provide:
- `MockWorld` and `MockRobot` abstractions to simulate warehouse-like environments.
- A scenario format (YAML) describing robot goals, humans, obstacles, and expected events.
- A `ScenarioRunner` that can run scenarios:
  - without guard (baseline behavior)
  - with guard (using `partenit-agent-guard`)
- A CLI (`partenit-bench`) to run and report on scenarios.

Built-in scenarios (planned):
- `human_crossing_path`
- `degraded_sensor`
- `policy_conflict`
- `blind_spot`
- `llm_unsafe_command`

The exact API and scenario schema are detailed in `IMPLEMENTATION_PLAN.md`.

[<img src="../../../partenit_robot.png" alt="Partenit robot" width="320" />](https://partenit.io)

Made with love for the future at [Partenit](https://partenit.io).

