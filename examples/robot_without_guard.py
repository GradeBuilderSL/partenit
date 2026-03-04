"""
robot_without_guard.py — baseline unsafe robot behavior.

The robot moves at full speed with no safety checks.
Compare with robot_with_guard.py to see the difference.

Run:
    python examples/robot_without_guard.py
"""

from partenit.adapters import MockRobotAdapter

# Set up the scene — human at 1.2m from the robot
adapter = MockRobotAdapter(robot_id="unsafe-robot")
adapter.add_human("worker-1", x=1.2, y=0.0)
adapter.add_object("pallet-1", "pallet", x=5.0, y=1.0)

observations = adapter.get_observations()

print("=== NO GUARD — Baseline Unsafe Behavior ===\n")
print(f"Detected {len(observations)} objects:")
for obs in observations:
    print(
        f"  {obs.object_id}: {obs.class_best} "
        f"@ {obs.distance():.1f}m "
        f"(treat_as_human={obs.treat_as_human})"
    )

# Without guard: execute at full speed regardless
params = {"zone": "shipping", "speed": 2.0}
print(f"\nExecuting: navigate_to {params}")
print("  → No safety check performed")
print("  → Speed: 2.0 m/s (UNSAFE near human at 1.2m)")
print("\n⚠ Robot runs at full speed past a human 1.2m away.")
print("  This is what Partenit prevents — see robot_with_guard.py")
