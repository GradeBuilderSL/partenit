# Partenit × Isaac Sim — H1 Safety Demo

This example shows how to use **Partenit tools** with a robot in **NVIDIA Isaac Sim**: safety guard in the loop, decision logging, safety grading (A–F), and policy tuning — so you can test and debug safety before moving to real hardware.

---

## For robot developers: what you get

| Partenit tool | What it does in this demo | When to use it |
|---------------|---------------------------|----------------|
| **GuardedRobot** | Every `navigate_to` goes through the guard; H1 gets allowed speed, clamped speed, or stop. | Add safety in the loop in sim or on the real robot. |
| **partenit-log replay** | Timeline of decisions (allowed / modified / blocked) in the terminal and as HTML. | After a run: “Why did it stop?” or share a run. |
| **partenit-eval** | Runs a scenario with and without guard; outputs grade A–F and report. | Answer “Is my controller safe?” or compare policies. |
| **partenit-policy sim** | For a given distance/speed, shows which rules fire and the result. | Tune policy thresholds without running the sim. |

Full guide: [docs/guides/isaac-sim.md](../../docs/guides/isaac-sim.md).

---

## Quick start (two terminals)

### Terminal 1 — start the bridge in Isaac Sim

Use the **Python that ships with Isaac Sim** (not system Python). Example for a source build:

```bash
cd examples/isaac_sim/
# Replace with your Isaac Sim Python, e.g.:
#   .../isaacsim/_build/linux-x86_64/release/python.sh
#   or set ISAAC_SIM_PYTHON
python.sh h1_bridge.py
```

Wait until you see:

```
Bridge API  : http://0.0.0.0:8000
[Bridge] Physics ready — Partenit API accepting commands
```

### Terminal 2 — run Partenit (from repo root)

**Minimal (one guarded command, see decision in console):**

```bash
python examples/isaac_sim/minimal_guard_demo.py
```

**Full demo (health check, GuardedRobot steps, eval, log replay, policy sim):**

```bash
python examples/test_h1_isaac.py
```

Keep Isaac Sim running until the script finishes.

---

## What we're doing and why

- Every decision (allow / clamp / block) is **sent to the bridge**. When the guard blocks (e.g. human too close), the bridge sets robot velocity to **zero** so the H1 stops.
- **Goal:** Show that Partenit in the loop keeps the robot safe: clamp speed when the human is near, full stop when too close; all decisions are logged and visible.

---

## Components in this folder

| File | Role |
|------|------|
| `h1_bridge.py` | Runs inside Isaac Sim — warehouse scene, H1, human; HTTP API on port 8000. |
| `minimal_guard_demo.py` | One-shot: one `navigate_to`, print decision; run from repo root. |
| `sim_frontend.py` | Omniverse UI panel (chat, scenarios). |
| `sim_camera.py` | H1 head camera capture. |
| `env_loader.py` | Loads `.env` (camera, API keys). |

The full test runner is `../../test_h1_isaac.py` (from repo root).

---

## Prerequisites

- NVIDIA Isaac Sim 4.x or 5.x
- Isaac Sim Python for running `h1_bridge.py`
- In your **local** env (for Terminal 2):  
  `pip install partenit-core partenit-agent-guard partenit-safety-bench partenit-adapters`

---

## Scene and policies

- **Scene:** H1 at (0, 0), human at (3.5, 0). Guard: distance &lt; 1.5 m → speed clamped to 0.3 m/s; &lt; 0.8 m → block.
- **Use in your code:** Same as with Mock or ROS2 — only the adapter changes:

```python
from partenit.adapters.isaac_sim import IsaacSimAdapter
from partenit.agent_guard import GuardedRobot

adapter = IsaacSimAdapter(base_url="http://localhost:8000")
robot = GuardedRobot(
    adapter=adapter,
    policy_path="examples/warehouse/policies.yaml",
    session_name="my_run",
)
decision = robot.navigate_to(zone="forward", speed=2.0)
robot.stop()
```

---

## Manual control and API

While the bridge is running, the Isaac Sim window accepts:

| Key | Action |
|-----|--------|
| ↑ / ↓ / ← / → | Move H1 |
| Esc | Stop |

HTTP: `GET /partenit/health`, `GET /partenit/observations`, `POST /partenit/command` (see [robot adapter spec](../../schemas/robot-adapter-api.yaml)).

---

## Extending

- More humans: edit `_HUMAN_WORLD_POS` and the `/partenit/observations` handler in `h1_bridge.py`.
- Other robots (G1, B2): change `usd_path` and the policy class in `h1_bridge.py`.
