"""
ros2_demo.py — Partenit guard with a generic ROS2 robot.

This demo requires ROS2 to be installed and sourced in the environment.
Without ROS2, importing ROS2Adapter raises ImportError (expected and documented).

Topics (configurable):
  Consumed: /partenit/observations  (partenit_msgs/ObservationArray)
  Published: /partenit/command      (partenit_msgs/GuardDecision)

Quick start (with ROS2):
    source /opt/ros/humble/setup.bash
    python examples/ros2_demo.py

Simulation alternative (no ROS2 needed):
    python examples/robot_with_guard.py
"""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    try:
        from partenit.adapters.ros2 import ROS2Adapter
    except ImportError as exc:
        print(f"ROS2 not available: {exc}")
        print("Install a ROS2 distribution and source its setup.bash.")
        print("See: https://docs.ros.org/en/humble/Installation.html")
        return

    from partenit.agent_guard import AgentGuard
    from partenit.decision_log import DecisionLogger

    adapter = ROS2Adapter(node_name="partenit_guard_demo")
    guard = AgentGuard()
    guard.load_policies(Path(__file__).parent / "warehouse" / "policies.yaml")
    logger = DecisionLogger()

    # In a real deployment this would run in a loop / ROS2 timer callback.
    observations = adapter.get_observations()

    action = "navigate_to"
    params = {"zone": "assembly", "speed": 1.0}
    context = {"source": "ros2"}

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

    # Send the (possibly modified) decision back to the robot via ROS2.
    adapter.send_decision(decision)

    print("=== ROS2 Demo ===")
    print(f"Action:      {action} {params}")
    print(f"Allowed:     {decision.allowed}")
    print(f"Risk score:  {decision.risk_score.value:.2f}")
    if decision.modified_params:
        print(f"Modified:    {decision.modified_params}")
    if not decision.allowed:
        print(f"Blocked:     {decision.rejection_reason}")
    print(f"Packet ID:   {packet.packet_id}")
    print(f"Fingerprint: {packet.fingerprint}")
    print(f"Verified:    {logger.verify_packet(packet)}")

    adapter.destroy()


if __name__ == "__main__":
    main()
