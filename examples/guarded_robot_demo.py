"""
GuardedRobot Demo — 1-line safety guard integration.

Shows how to add Partenit safety guard to any robot in one line.
Compare with robot_without_guard.py (unsafe) and robot_with_guard.py (low-level API).

Run:
    python examples/guarded_robot_demo.py
"""

from pathlib import Path

from partenit.adapters import MockRobotAdapter
from partenit.agent_guard import GuardedRobot

# ── Setup ─────────────────────────────────────────────────────────────────────
# Prepare adapter — add a worker close to the robot path
adapter = MockRobotAdapter(robot_id="demo-robot")
adapter.add_human("worker-1", x=1.2, y=0.0)  # human at 1.2 m
adapter.add_object("pallet-1", "pallet", x=5.0, y=2.0)

# This is all you need.  GuardedRobot wraps adapter + guard + logger.
robot = GuardedRobot(
    adapter=adapter,
    policy_path=Path(__file__).parent / "warehouse" / "policies.yaml",
    session_name="guarded_robot_demo",
)

print("=== GuardedRobot Demo ===\n")
print(repr(robot))
print()

# ── Navigation with automatic guard ──────────────────────────────────────────
print("Action 1: navigate_to shipping at 2.0 m/s (human nearby)")
decision = robot.navigate_to(zone="shipping", speed=2.0)
print(f"  Allowed:  {decision.allowed}")
if decision.modified_params:
    original = 2.0
    clamped = decision.modified_params.get("speed", original)
    print(f"  Speed:    {original} → {clamped} m/s  (clamped by guard)")
print(f"  Risk:     {robot.risk_score:.2f}")
print(f"  Policies: {decision.applied_policies}")
print()

# ── Action 2: lower speed — guard should allow ────────────────────────────────
print("Action 2: navigate_to storage at 0.3 m/s (slow, should be allowed)")
decision = robot.navigate_to(zone="storage", speed=0.3)
print(f"  Allowed:  {decision.allowed}")
print(f"  Risk:     {robot.risk_score:.2f}")
print(f"  Params:   {decision.modified_params or 'no modification'}")
print()

# ── Last decision and events ──────────────────────────────────────────────────
print(f"Total safety events this session: {len(robot.events)}")
for evt in robot.events:
    print(f"  [{evt.event_type}] triggered_by={evt.triggered_by} severity={evt.severity}")

print()
print("Session decisions are saved to: decisions/guarded_robot_demo/")
print()
print("Compare with:")
print("  python examples/robot_without_guard.py   ← no safety checks")
print("  python examples/robot_with_guard.py      ← low-level API")
