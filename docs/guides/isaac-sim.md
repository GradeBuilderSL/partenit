# Using Partenit with NVIDIA Isaac Sim

This guide is for **robot developers** who build or test robots in NVIDIA Isaac Sim and want to add safety validation, logging, and grading with Partenit — without changing their sim pipeline.

---

## Why use Partenit in Isaac Sim?

| Goal | What Partenit gives you |
|------|-------------------------|
| **Safety in the loop** | Every move command goes through the guard; speed is clamped or blocked near humans. Same policies work in sim and on the real robot. |
| **Explainable decisions** | You see which policy fired (e.g. `human_proximity_slowdown`), risk score, and modified params in the console and in logs. |
| **Audit trail** | Every decision is stored as a signed `DecisionPacket`; you can replay the timeline later or verify integrity with `partenit-log`. |
| **Safety grade (A–F)** | Run `partenit-eval` to compare baseline vs guarded controller on the same scenario and get a single grade. |
| **Tune policies offline** | Use `partenit-policy sim` to see which rules fire at a given distance/speed — no need to run the sim. |

You keep using Isaac Sim for physics and rendering; Partenit sits between your planner and the sim as a **middleware** that only allows safe commands through.

---

## Architecture in one picture

```
Your code (or test script)
    ↓  navigate_to(zone="forward", speed=2.0)
GuardedRobot (partenit-agent-guard)
    ↓  get_observations() from adapter → guard checks policies
IsaacSimAdapter (partenit-adapters)
    ↓  HTTP: GET /partenit/observations, POST /partenit/command
H1 Bridge (runs inside Isaac Sim)
    ↓  reads H1 pose, human pose → returns observations
    ↓  applies allowed speed or stop to H1
Isaac Sim (physics + H1 robot)
```

Only the **adapter** and the **bridge** are Isaac-specific. The guard, policies, decision log, and eval tools are the same for Mock, ROS2, or real hardware.

---

## Quick start (H1 + warehouse scene)

We provide a ready-made bridge and test so you can see the full loop in a few minutes.

### 1. Start the bridge inside Isaac Sim

Use the **Python that ships with Isaac Sim** (not your system Python). Example for a source build:

```bash
cd examples/isaac_sim/
# Use your Isaac Sim Python; common paths:
#   Source build:  /path/to/isaacsim/_build/linux-x86_64/release/python.sh
#   Omniverse:    ~/.local/share/ov/pkg/isaac-sim-*/python.sh
python.sh h1_bridge.py
```

Or set `ISAAC_SIM_PYTHON` to the path of `python.sh` and run:

```bash
$ISAAC_SIM_PYTHON h1_bridge.py
```

Wait until you see:

```
Bridge API  : http://0.0.0.0:8000
[Bridge] Physics ready — Partenit API accepting commands
```

### 2. Run a minimal guard demo (one command)

From the **project root**, with your normal Python (venv with Partenit installed):

```bash
python examples/isaac_sim/minimal_guard_demo.py
```

You’ll see one `navigate_to` request, the guard’s decision (allowed / modified / blocked), risk score, and applied policies. The H1 in the Sim window will move or stop according to that decision.

### 3. Run the full toolkit demo

```bash
python examples/test_h1_isaac.py
```

This runs five steps: health + observations, GuardedRobot with several speeds, partenit-eval (grade A–F), partenit-log replay (timeline), and partenit-policy sim (which rules fire at 1.0 m). Keep Isaac Sim open until it finishes.

---

## Partenit tools you get in this example

| Tool | What it does in the Isaac Sim demo | When you’d use it as a developer |
|------|------------------------------------|-----------------------------------|
| **GuardedRobot** | Sends each `navigate_to` through the guard; H1 only gets allowed or clamped speed, or stop. | Any time you want “safety in the loop” in sim or on the robot. |
| **partenit-log replay** | Prints a timeline of decisions (allowed / modified / blocked) and writes HTML. | After a run: “Why did the robot stop at t=5?” or to share a run with the team. |
| **partenit-eval** | Runs a scenario (e.g. human crossing) with and without guard and outputs a grade (A–F). | To check “is my controller safe?” or compare two policy sets. |
| **partenit-policy sim** | Given distance/speed/action, shows which policies fire and the resulting speed/block. | To tune thresholds (e.g. 1.2 m vs 1.5 m) without running the sim. |

---

## Use GuardedRobot in your own script

Same pattern as with Mock or ROS2 — only the adapter changes:

```python
from pathlib import Path
from partenit.adapters.isaac_sim import IsaacSimAdapter
from partenit.agent_guard import GuardedRobot

adapter = IsaacSimAdapter(base_url="http://localhost:8000")
robot = GuardedRobot(
    adapter=adapter,
    policy_path=Path("examples/warehouse/policies.yaml"),
    session_name="my_isaac_run",
)

# One guarded command — guard may allow, clamp speed, or block
decision = robot.navigate_to(zone="forward", speed=2.0)
print(decision.allowed, decision.modified_params, decision.applied_policies)

# Always send stop when done
robot.stop()
```

The bridge must be running in Isaac Sim and expose the [standard Partenit HTTP API](../vendor/robot-adapter-spec.md) on port 8000 (or the URL you pass to `IsaacSimAdapter`).

---

## Bridge API (for your own scenes)

If you add another robot or scene in Isaac Sim, implement the same contract:

| Endpoint | Description |
|----------|-------------|
| `GET /partenit/health` | `{ "status": "ok", "robot_id": "...", "ready": true }` when physics is running. |
| `GET /partenit/observations` | List of objects (e.g. humans) as Partenit `StructuredObservation` (robot-centric positions, `class_best`, etc.). |
| `POST /partenit/command` | Body: Partenit `GuardDecision` JSON. If `allowed` is false, set robot velocity to zero; otherwise apply `modified_params` (e.g. speed). |

See [Robot adapter API spec](../vendor/robot-adapter-spec.md) and the H1 bridge implementation in `examples/isaac_sim/h1_bridge.py`.

---

## What to read next

- [Simulation guide](simulation.md) — MockRobotAdapter and scenario YAML (no Isaac).
- [Writing policies](writing-policies.md) — define and validate your own safety rules.
- [Custom robot (HTTP)](custom-robot.md) — connect any robot that speaks the Partenit HTTP API.
