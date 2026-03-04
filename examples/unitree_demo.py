"""
unitree_demo.py — Partenit guard with a Unitree robot via ROS2.

This demo assumes:
- ROS2 is installed and sourced in the environment.
- Unitree publishes its state to ROS2 topics that the base ROS2Adapter
  (and by extension UnitreeAdapter) can consume.

In environments without ROS2, running this script will raise
an ImportError from the adapter, which is expected.
"""

from __future__ import annotations

from pathlib import Path

from partenit.adapters.unitree import UnitreeAdapter
from partenit.agent_guard import AgentGuard
from partenit.decision_log import DecisionLogger


def main() -> None:
    adapter = UnitreeAdapter(node_name="partenit_unitree_demo")
    guard = AgentGuard()
    guard.load_policies(Path(__file__).parent / "warehouse" / "policies.yaml")
    logger = DecisionLogger()

    observations = adapter.get_observations()

    action = "navigate_to"
    params = {"zone": "loading", "speed": 1.2}
    context = {"source": "unitree"}

    decision = guard.check_action(
        action=action,
        params=params,
        context=context,
        observations=observations,
    )

    packet = logger.create_packet(
        action_requested=action,
        action_params=params,
        guard_decision=decision,
        observation_hashes=[obs.frame_hash for obs in observations if obs.frame_hash],
    )

    adapter.send_decision(decision)

    print("=== Unitree Demo ===")
    print(f"Action:      {action} {params}")
    print(f"Allowed:     {decision.allowed}")
    print(f"Risk score:  {decision.risk_score.value:.2f}")
    print(f"Packet ID:   {packet.packet_id}")
    print(f"Fingerprint: {packet.fingerprint}")
    print(f"Verified:    {logger.verify_packet(packet)}")


if __name__ == "__main__":
    main()

