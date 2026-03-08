"""
isaac_sim_demo.py — Partenit guard with an Isaac Sim robot via HTTP gateway.

This demo assumes you have an Isaac Sim scene running and a small HTTP
gateway that exposes the standard Partenit robot API:

    GET  /partenit/observations  -> StructuredObservation[]
    POST /partenit/command       <- GuardDecision
    GET  /partenit/health        -> {status, robot_id, timestamp}

The details of that gateway are simulator-specific and live outside
this repository. Here we only show how to plug it into Partenit.
"""

from __future__ import annotations

from pathlib import Path

from partenit.adapters.isaac_sim import IsaacSimAdapter
from partenit.agent_guard import AgentGuard
from partenit.decision_log import DecisionLogger


def main() -> None:
    # H1 bridge in examples/isaac_sim/ uses port 8000
    adapter = IsaacSimAdapter(base_url="http://localhost:8000", robot_id="isaac-sim-demo")

    guard = AgentGuard()
    policies_path = Path(__file__).parent / "warehouse" / "policies.yaml"
    guard.load_policies(policies_path)

    logger = DecisionLogger()

    # 1) Read observations from the simulation gateway
    observations = adapter.get_observations()

    # 2) Ask guard to evaluate a navigation action
    action = "navigate_to"
    params = {"zone": "shipping", "speed": 1.8}
    context = {"source": "isaac_sim"}

    decision = guard.check_action(
        action=action,
        params=params,
        context=context,
        observations=observations,
    )

    # 3) Log the decision (always — even if blocked)
    packet = logger.create_packet(
        action_requested=action,
        action_params=params,
        guard_decision=decision,
        observation_hashes=[obs.frame_hash for obs in observations if obs.frame_hash],
    )

    # 4) Send the decision back to the simulated robot
    adapter.send_decision(decision)

    print("=== Isaac Sim Demo ===")
    print(f"Action:      {action} {params}")
    print(f"Allowed:     {decision.allowed}")
    print(f"Risk score:  {decision.risk_score.value:.2f}")
    print(f"Packet ID:   {packet.packet_id}")
    print(f"Fingerprint: {packet.fingerprint}")
    print(f"Verified:    {logger.verify_packet(packet)}")


if __name__ == "__main__":
    main()
