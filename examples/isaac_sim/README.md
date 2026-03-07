# Partenit × Isaac Sim — H1 Safety Demo

Run the full Partenit safety stack on a **Unitree H1** humanoid robot inside
**NVIDIA Isaac Sim** — with a real physics simulation, a live Omniverse UI panel,
and automatic grading (A–F) of your safety controller.

## What you get

| Component | What it does |
|-----------|-------------|
| `h1_bridge.py` | Runs inside Isaac Sim — loads warehouse scene, H1 robot, human mannequin. Exposes HTTP API on port 8000. |
| `sim_frontend.py` | Omniverse UI panel: chat, scenario buttons, enable/disable brain. |
| `sim_camera.py` | H1 head camera capture (PNG → VLM-ready bytes). |
| `env_loader.py` | Loads `.env` settings (camera params, API keys). |
| `../../examples/test_h1_isaac.py` | Test runner: connects Partenit tools to the live bridge. |

## Prerequisites

- NVIDIA Isaac Sim 4.x or 5.x installed and licensed
- Isaac Sim Python environment activated (the one that ships with Isaac Sim)
- `pip install partenit-core partenit-agent-guard partenit-safety-bench partenit-adapters` inside that environment

## Run order

**Terminal 1 — start Isaac Sim with the bridge:**

```bash
cd examples/isaac_sim/
python h1_bridge.py
```

Wait for:
```
Bridge API  : http://0.0.0.0:8000
Partenit API: http://0.0.0.0:8000/partenit/{health,observations,command}
[Bridge] Warehouse: .../Simple_Warehouse/full_warehouse.usd
[Bridge] Human at world (3.5, 0.0, 0.0)
[Bridge] GUI ready
[Bridge] Arrow keys — manual control | Partenit API — autonomous guard
```

**Terminal 2 — run the Partenit test suite:**

```bash
python examples/test_h1_isaac.py
```

This runs 5 steps automatically:
1. Health check — verifies the bridge is reachable
2. GuardedRobot — sends H1 toward the human with increasing speed; watch clamp/block
3. partenit-eval — grades baseline vs guarded (A–F) with SVG report
4. partenit-log replay — prints decision timeline in the terminal
5. partenit-policy sim — shows which policies fired at distance 1.0 m

## Manual keyboard control

While the bridge is running, the Isaac Sim window accepts keyboard input:

| Key | Action |
|-----|--------|
| ↑ | Forward 0.75 m/s |
| ↓ | Backward 0.5 m/s |
| ← | Rotate left |
| → | Rotate right |
| Esc | Stop |

## Bridge HTTP API

```bash
# Check bridge is up
curl http://localhost:8000/partenit/health

# Get human position relative to H1
curl http://localhost:8000/partenit/observations

# Get H1 state (position, velocity, heading)
curl http://localhost:8000/robot/state

# Move H1 manually
curl -X POST http://localhost:8000/control/move \
     -H "Content-Type: application/json" \
     -d '{"vx": 0.5, "vy": 0.0, "wz": 0.0}'

# Stop
curl -X POST http://localhost:8000/control/stop
```

## Connect from your own code

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
print(decision.allowed)           # False — guard blocked (human too close)
print(decision.risk_score.value)  # 0.91
print(decision.applied_policies)  # ['emergency_stop_human']
```

## Scene layout

```
          Human (3.5, 0)
              🧍
              │  ← 3.5 m
             ═╪═══════════════ H1 start (0, 0)
                               🤖
```

The guard fires at:
- **distance < 1.5 m** → speed clamped to 0.3 m/s (`human_proximity_slowdown`)
- **distance < 0.8 m** → fully blocked (`emergency_stop_human`)

## Expected output (step 2)

```
  speed   dist      result  final   risk  policies
  ─────  ─────  ──────────  ─────  ─────  ────────────────
    0.3   3.50      allowed    0.3   0.10  —
    0.6   3.50      allowed    0.6   0.18  —
    1.0   3.50      allowed    1.0   0.24  —
    1.5   1.20     MODIFIED    0.3   0.58  human_proximity_slowdown
    2.0   0.70      BLOCKED    0.0   0.91  emergency_stop_human
```

## Extending the scene

To add more humans or change their positions, edit `_HUMAN_WORLD_POS` in
`h1_bridge.py` and update the `/partenit/observations` handler to return
multiple observations.

To replace H1 with G1 or B2, change the `usd_path` and `H1FlatTerrainPolicy`
to the corresponding Isaac Sim robot asset and policy class.
