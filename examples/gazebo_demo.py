"""
gazebo_demo.py — Partenit guard with a Gazebo-simulated robot via HTTP gateway.

This demo assumes you have a Gazebo scene running and a small HTTP
gateway that exposes the standard Partenit robot API:

    GET  /partenit/observations  -> StructuredObservation[]
    POST /partenit/command       <- GuardDecision
    GET  /partenit/health        -> {status, robot_id, timestamp}

The gateway can be:
- A ROS2 node (if using Gazebo via ROS2) — see ros2-robot.md guide
- A standalone Python bridge reading Gazebo state via gz-transport

The Partenit side is identical regardless of which gateway you use.
"""

from __future__ import annotations

from pathlib import Path

from partenit.adapters.gazebo import GazeboAdapter
from partenit.agent_guard import AgentGuard
from partenit.decision_log import DecisionLogger


def main() -> None:
    adapter = GazeboAdapter(base_url="http://localhost:7001", robot_id="gazebo-demo")

    guard = AgentGuard()
    policies_path = Path(__file__).parent / "warehouse" / "policies.yaml"
    guard.load_policies(policies_path)

    logger = DecisionLogger()

    observations = adapter.get_observations()

    action = "navigate_to"
    params = {"zone": "shipping", "speed": 1.5}
    context: dict = {}
    for obs in observations:
        if obs.treat_as_human:
            d = obs.distance()
            if not context.get("human") or d < context["human"]["distance"]:
                context["human"] = {"distance": d, "object_id": obs.object_id}

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

    print("=== Gazebo Demo ===")
    print(f"Action:      {action} {params}")
    print(f"Allowed:     {decision.allowed}")
    print(f"Risk score:  {decision.risk_score.value:.2f}")
    print(f"Packet ID:   {packet.packet_id}")
    print(f"Verified:    {logger.verify_packet(packet)}")


if __name__ == "__main__":
    main()
