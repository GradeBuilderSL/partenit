#!/usr/bin/env python3
"""
Minimal Partenit guard demo with Isaac Sim (H1 bridge).

Shows one guarded navigate_to: you see the decision (allowed / modified / blocked),
risk score, and applied policies. The H1 in the Sim window moves or stops accordingly.

Prerequisites:
  1. Isaac Sim running with the H1 bridge: from examples/isaac_sim/ run
       <isaac_sim_python.sh> h1_bridge.py
  2. Partenit installed in this environment: pip install partenit-core partenit-agent-guard partenit-adapters

Usage (from repo root):
    python examples/isaac_sim/minimal_guard_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root so "examples/warehouse/policies.yaml" resolves
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from partenit.adapters.isaac_sim import IsaacSimAdapter
from partenit.agent_guard import GuardedRobot

BRIDGE_URL = "http://localhost:8000"
POLICY_PATH = Path(__file__).resolve().parent.parent / "warehouse" / "policies.yaml"


def main() -> int:
    print("Connecting to Isaac Sim bridge at", BRIDGE_URL, "...")
    adapter = IsaacSimAdapter(base_url=BRIDGE_URL)
    health = adapter.get_health()
    if health.get("status") != "ok":
        print("ERROR: Bridge not reachable. Start the bridge in Isaac Sim first:")
        print("  cd examples/isaac_sim/")
        print("  <your Isaac Sim python.sh> h1_bridge.py")
        return 1
    if not health.get("ready"):
        print("WARNING: Physics not ready yet; observations may be stale. Wait for '[Bridge] Physics ready'.")

    robot = GuardedRobot(
        adapter=adapter,
        policy_path=str(POLICY_PATH),
        session_name="minimal_demo",
    )

    # One guarded command — guard may allow, clamp, or block
    requested_speed = 1.5
    print(f"\nRequesting: navigate_to(zone='forward', speed={requested_speed})")
    decision = robot.navigate_to(zone="forward", speed=requested_speed)

    obs = adapter.get_observations()
    dist = obs[0].distance() if obs else float("nan")
    print(f"  Human distance: {dist:.2f} m")
    print(f"  Decision:       {'ALLOWED' if decision.allowed else 'BLOCKED'}")
    if decision.modified_params:
        print(f"  Modified params: {decision.modified_params}")
    print(f"  Risk score:     {decision.risk_score.value:.2f}" if decision.risk_score else "  Risk score:     —")
    print(f"  Applied rules:  {decision.applied_policies or '—'}")
    print("\nCheck the Isaac Sim window: H1 should have moved or stopped according to the decision.")
    robot.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
