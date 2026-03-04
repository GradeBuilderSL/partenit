"""
robot_with_guard.py — same scenario as robot_without_guard.py, but safe.

AgentGuard intercepts the action, evaluates policies, clamps speed,
and logs the decision with a cryptographic fingerprint.

Run:
    python examples/robot_with_guard.py
"""

from pathlib import Path

from partenit.adapters import MockRobotAdapter
from partenit.agent_guard import AgentGuard
from partenit.decision_log import DecisionLogger

# --- Setup ---
adapter = MockRobotAdapter(robot_id="guarded-robot")
adapter.add_human("worker-1", x=1.2, y=0.0)
adapter.add_object("pallet-1", "pallet", x=5.0, y=1.0)

guard = AgentGuard()
guard.load_policies(Path(__file__).parent / "warehouse" / "policies.yaml")

log = DecisionLogger()

# --- Get observations ---
observations = adapter.get_observations()

print("=== WITH GUARD — Safe Behavior ===\n")
print(f"Detected {len(observations)} objects:")
for obs in observations:
    print(
        f"  {obs.object_id}: {obs.class_best} "
        f"@ {obs.distance():.1f}m "
        f"(treat_as_human={obs.treat_as_human})"
    )

# --- Check action with guard ---
action = "navigate_to"
params = {"zone": "shipping", "speed": 2.0}
context = {"human": {"distance": 1.2}}

print(f"\nRequested: {action} {params}")

decision = guard.check_action(
    action=action,
    params=params,
    context=context,
    observations=observations,
)

# --- Log the decision (always — even if blocked) ---
packet = log.create_packet(
    action_requested=action,
    action_params=params,
    guard_decision=decision,
    observation_hashes=[obs.frame_hash for obs in observations if obs.frame_hash],
)

# --- Report ---
if decision.allowed:
    effective_params = decision.modified_params or params
    print(f"\n✓ ALLOWED — executing with params: {effective_params}")
    print(f"  Applied policies: {decision.applied_policies}")
    print(f"  Risk score: {decision.risk_score.value:.2f}")
    if decision.modified_params:
        print(f"  Speed clamped: {params['speed']} → {effective_params.get('speed')} m/s")
else:
    print(f"\n✗ BLOCKED — {decision.rejection_reason}")
    print(f"  Risk score: {decision.risk_score.value:.2f}")

print(f"\nDecisionPacket: {packet.packet_id}")
print(f"Fingerprint:    {packet.fingerprint}")
print(f"Verified:       {log.verify_packet(packet)}")
