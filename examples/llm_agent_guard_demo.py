"""
llm_agent_guard_demo.py — AgentGuard as a safety layer for LLM tool calls.

This demo shows how to insert partenit-agent-guard between an LLM
with tool-calling capabilities and environment-affecting robot actions.

Architecture:
    LLM (Anthropic Claude)
        ↓  proposes tool calls
    AgentGuard
        ↓  evaluates against safety policies
    Robot / Simulator (MockRobotAdapter)
        ↓  executes (or rejects) actions
    DecisionLogger
        ↓  creates cryptographic audit record

Run:
    python examples/llm_agent_guard_demo.py

Note: This demo works WITHOUT an API key using simulated LLM responses.
To use real Claude, set ANTHROPIC_API_KEY and pass --real-llm flag.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from partenit.adapters import MockRobotAdapter
from partenit.agent_guard import AgentGuard
from partenit.decision_log import DecisionLogger

# ---------------------------------------------------------------------------
# Tool definitions (what the LLM can call)
# These are the "robot actions" the LLM agent wants to execute.
# ---------------------------------------------------------------------------

ROBOT_TOOLS = [
    {
        "name": "navigate_to",
        "description": "Move the robot to a target zone or coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "zone": {
                    "type": "string",
                    "description": "Target zone name, e.g. 'shipping', 'storage'",
                },
                "speed": {"type": "number", "description": "Speed in m/s (0.0 – 3.0)"},
            },
            "required": ["zone", "speed"],
        },
    },
    {
        "name": "pick_object",
        "description": "Pick up an object by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "string", "description": "ID of the object to pick"},
                "force_kg": {"type": "number", "description": "Grip force in kg (0.1 – 5.0)"},
            },
            "required": ["object_id", "force_kg"],
        },
    },
    {
        "name": "emergency_stop",
        "description": "Immediately stop all robot motion.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Simulated LLM responses (used when --real-llm is not set)
# ---------------------------------------------------------------------------

SIMULATED_MISSION = """
Mission: deliver pallet-1 to the shipping zone as fast as possible.
A worker (worker-1) is currently 1.2 meters away from the robot.
"""

SIMULATED_TOOL_CALLS = [
    # First call: LLM tries to navigate fast (will be clamped by guard)
    {
        "name": "navigate_to",
        "input": {"zone": "pallet-storage", "speed": 2.5},
        "llm_reasoning": "Moving at 2.5 m/s to reach the pallet quickly.",
    },
    # Second call: pick the pallet
    {
        "name": "pick_object",
        "input": {"object_id": "pallet-1", "force_kg": 3.0},
        "llm_reasoning": "Picking pallet-1 with adequate grip force.",
    },
    # Third call: navigate to shipping zone at dangerous speed near human
    {
        "name": "navigate_to",
        "input": {"zone": "shipping", "speed": 3.0},
        "llm_reasoning": "Full speed to deliver pallet to shipping zone.",
    },
]


# ---------------------------------------------------------------------------
# Guard + adapter setup
# ---------------------------------------------------------------------------


def build_scene() -> MockRobotAdapter:
    adapter = MockRobotAdapter(robot_id="llm-controlled-robot")
    adapter.add_human("worker-1", x=1.2, y=0.0)
    adapter.add_object("pallet-1", "pallet", x=3.0, y=0.5)
    return adapter


def build_guard() -> AgentGuard:
    guard = AgentGuard()
    policies_path = Path(__file__).parent / "warehouse" / "policies.yaml"
    if policies_path.exists():
        n = guard.load_policies(policies_path)
        print(f"[Guard] Loaded {n} policies from {policies_path.name}")
    else:
        print("[Guard] No policy file found — running with no policies (allow all)")
    return guard


# ---------------------------------------------------------------------------
# Core loop: iterate over tool calls, guard each one
# ---------------------------------------------------------------------------


def run_demo(use_real_llm: bool = False) -> None:
    print("=" * 60)
    print("  Partenit LLM Agent Guard Demo")
    print("=" * 60)

    adapter = build_scene()
    guard = build_guard()
    log = DecisionLogger()

    observations = adapter.get_observations()
    print(f"\n[World] {len(observations)} objects detected:")
    for obs in observations:
        print(
            f"  {obs.object_id}: {obs.class_best} "
            f"@ {obs.distance():.1f}m "
            f"(treat_as_human={obs.treat_as_human})"
        )

    tool_calls = _get_tool_calls(use_real_llm)

    print(f"\n[LLM] Mission: {SIMULATED_MISSION.strip()}")
    print(f"\n[LLM] Proposing {len(tool_calls)} tool calls...\n")
    print("-" * 60)

    results: list[dict] = []

    for i, call in enumerate(tool_calls, start=1):
        action = call["name"]
        params = call["input"]
        reasoning = call.get("llm_reasoning", "No reasoning provided")

        print(f"\n[{i}] LLM proposes: {action}({json.dumps(params)})")
        print(f"    Reasoning: {reasoning}")

        # Build context for the guard from current observations
        context: dict = {}
        for obs in observations:
            if obs.treat_as_human:
                existing = context.get("human", {})
                d = obs.distance()
                if not existing or d < existing.get("distance", float("inf")):
                    context["human"] = {
                        "distance": d,
                        "object_id": obs.object_id,
                    }

        decision = guard.check_action(
            action=action,
            params=params,
            context=context,
            observations=observations,
        )

        packet = log.create_packet(
            action_requested=action,
            action_params=params,
            guard_decision=decision,
            observation_hashes=[obs.frame_hash for obs in observations if obs.frame_hash],
        )

        if decision.allowed:
            effective = decision.modified_params or params
            status = "ALLOWED"
            if decision.modified_params:
                status = "MODIFIED"
            print(f"    [Guard] {status} → {effective}")
            if decision.applied_policies:
                print(f"    [Guard] Applied: {decision.applied_policies}")
            print(f"    [Guard] Risk: {decision.risk_score.value:.2f}")
            adapter.send_decision(decision)
            results.append({"action": action, "status": status, "effective_params": effective})
        else:
            print(f"    [Guard] BLOCKED — {decision.rejection_reason}")
            print(f"    [Guard] Risk: {decision.risk_score.value:.2f}")
            results.append(
                {"action": action, "status": "BLOCKED", "reason": decision.rejection_reason}
            )

        print(f"    [Log]  Packet: {packet.packet_id[:16]}…  Verified: {log.verify_packet(packet)}")

    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    allowed = sum(1 for r in results if r["status"] in ("ALLOWED", "MODIFIED"))
    modified = sum(1 for r in results if r["status"] == "MODIFIED")
    blocked = sum(1 for r in results if r["status"] == "BLOCKED")
    print(f"  Total tool calls:  {len(results)}")
    print(f"  Allowed:           {allowed} ({modified} with modified params)")
    print(f"  Blocked:           {blocked}")
    all_packets = log.recent(100)
    print(f"  Decisions logged:  {len(all_packets)}")
    print("\n  Every decision has a cryptographic fingerprint.")
    print(
        f"  All {len(all_packets)} packets verified: {all(log.verify_packet(p) for p in all_packets)}"
    )
    print()
    print("  What this demo shows:")
    print("  - The LLM is free to reason and propose any action.")
    print("  - AgentGuard evaluates each proposal against safety policies.")
    print("  - Dangerous speed commands are clamped, not rejected.")
    print("  - All decisions — allowed and blocked — are logged.")
    print("  - Audit trail is tamper-evident via SHA256 fingerprints.")


# ---------------------------------------------------------------------------
# LLM call dispatch
# ---------------------------------------------------------------------------


def _get_tool_calls(use_real_llm: bool) -> list[dict]:
    if not use_real_llm:
        return SIMULATED_TOOL_CALLS

    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        print("[LLM] anthropic package not installed — falling back to simulated calls")
        print("      Install: pip install anthropic")
        return SIMULATED_TOOL_CALLS

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[LLM] ANTHROPIC_API_KEY not set — falling back to simulated calls")
        return SIMULATED_TOOL_CALLS

    client = anthropic.Anthropic(api_key=api_key)
    print("[LLM] Calling Claude claude-sonnet-4-6 with robot tools...")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=ROBOT_TOOLS,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are controlling a warehouse robot. "
                    f"{SIMULATED_MISSION}\n\n"
                    "Complete the mission by calling the appropriate tools. "
                    "Start with navigating to the pallet, then pick it, then deliver it."
                ),
            }
        ],
    )

    calls = []
    for block in response.content:
        if block.type == "tool_use":
            calls.append(
                {
                    "name": block.name,
                    "input": block.input,
                    "llm_reasoning": f"Claude proposed this via tool_use (id={block.id[:8]})",
                }
            )

    if not calls:
        print("[LLM] Claude returned no tool calls — using simulated calls as fallback")
        return SIMULATED_TOOL_CALLS

    return calls


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Partenit LLM Agent Guard Demo")
    parser.add_argument(
        "--real-llm",
        action="store_true",
        help="Use real Claude API (requires ANTHROPIC_API_KEY environment variable)",
    )
    args = parser.parse_args()

    run_demo(use_real_llm=args.real_llm)
