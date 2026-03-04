"""
llm_tool_guard_demo.py — LLMToolCallGuard intercepting LLM tool calls.

Demonstrates how to use LLMToolCallGuard as a drop-in safety gate
in any LLM orchestration loop (Anthropic, OpenAI, LangChain, etc.)

No LLM API key required — simulated tool calls are used.
The guard pattern is identical with a real LLM.
"""

from __future__ import annotations

from pathlib import Path

from partenit.adapters.llm_tool_calling import LLMToolCallGuard

POLICIES = Path(__file__).parent / "warehouse" / "policies.yaml"

SIMULATED_CALLS = [
    {
        "name": "navigate_to",
        "input": {"zone": "shipping", "speed": 2.5},
        "context": {"human": {"distance": 1.1}},
        "description": "LLM asks for 2.5 m/s near a human (should clamp)",
    },
    {
        "name": "navigate_to",
        "input": {"zone": "storage", "speed": 0.8},
        "context": {"human": {"distance": 5.0}},
        "description": "Safe speed, human far away (should allow)",
    },
    {
        "name": "navigate_to",
        "input": {"zone": "charging", "speed": 1.0},
        "context": {"human": {"distance": 0.5}},
        "description": "Human 0.5m away — should block",
    },
]


def main() -> None:
    guard = LLMToolCallGuard()
    guard.load_policies(POLICIES)

    print("=== LLM Tool Call Guard Demo ===\n")

    for call in SIMULATED_CALLS:
        print(f"Tool call: {call['name']}({call['input']})")
        print(f"Scenario:  {call['description']}")

        result = guard.check_tool_call(
            tool_name=call["name"],
            tool_input=call["input"],
            context=call["context"],
        )

        if result.allowed:
            status = "ALLOWED"
            if result.modified:
                status = f"CLAMPED → {result.safe_input}"
        else:
            status = f"BLOCKED — {result.decision.rejection_reason}"

        print(f"Result:    {status}")
        print(f"Risk:      {result.decision.risk_score.value:.2f}")
        print(f"Policies:  {result.decision.applied_policies}")

        if not result.allowed:
            print(f"LLM msg:   {result.rejection_message}")

        print()


if __name__ == "__main__":
    main()
