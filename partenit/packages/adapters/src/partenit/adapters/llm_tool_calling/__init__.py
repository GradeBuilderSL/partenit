"""
LLMToolCallGuard — intercepts LLM tool calls and validates them via AgentGuard.

This adapter bridges the gap between LLM frameworks (OpenAI function calling,
Anthropic tool use, LangChain, etc.) and the Partenit safety stack.

It is NOT a RobotAdapter — it operates at the LLM orchestration layer,
not the robot transport layer. Its job is to be the safety gate between
the LLM planner and any function/tool that can affect the physical world.

Architecture:
    LLM response
        ↓
    LLMToolCallGuard.check_tool_call()
        ↓ (uses AgentGuard + loaded policies)
    GuardedToolCall (allowed / blocked / modified)
        ↓
    Your execution layer

All safety logic lives in partenit-agent-guard.
This module is only a translation/convenience layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from partenit.agent_guard.core import AgentGuard
from partenit.core.models import GuardDecision


@dataclass
class GuardedToolCall:
    """Result of a guard check on an LLM tool call."""

    tool_name: str
    allowed: bool
    safe_input: dict[str, Any]          # original or modified input
    original_input: dict[str, Any]
    decision: GuardDecision
    rejection_message: str = ""         # human-readable, suitable for LLM context

    @property
    def modified(self) -> bool:
        return self.safe_input != self.original_input


class LLMToolCallGuard:
    """
    Drop-in safety layer for LLM tool/function calls.

    Wraps AgentGuard with a clean interface for LLM orchestration patterns.

    Usage:
        guard = LLMToolCallGuard()
        guard.load_policies("./policies/warehouse.yaml")

        # In your tool execution loop:
        result = guard.check_tool_call(
            tool_name="navigate_to",
            tool_input={"zone": "shipping", "speed": 2.0},
            context={"human": {"distance": 1.2}},
        )

        if result.allowed:
            execute_tool(result.tool_name, result.safe_input)
        else:
            # Feed rejection back to LLM for replanning
            llm.append_tool_error(result.rejection_message)
    """

    def __init__(self, guard: AgentGuard | None = None) -> None:
        self._guard = guard or AgentGuard()

    def load_policies(self, path: str) -> int:
        """Load policies from YAML file. Returns number of rules loaded."""
        return self._guard.load_policies(path)

    def check_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: dict[str, Any] | None = None,
        observations: list | None = None,
    ) -> GuardedToolCall:
        """
        Check a single LLM tool call against loaded policies.

        Args:
            tool_name: Function/tool name (e.g. "navigate_to", "pick_up")
            tool_input: Parameters the LLM wants to pass to the tool
            context: World context dict (humans, distances, trust levels, etc.)
            observations: Optional StructuredObservation list from sensors

        Returns:
            GuardedToolCall with allowed=True/False and safe_input
        """
        decision = self._guard.check_action(
            action=tool_name,
            params=tool_input,
            context=context or {},
            observations=observations or [],
        )

        if decision.allowed:
            safe_input = decision.modified_params or tool_input
            rejection_message = ""
        else:
            safe_input = {}
            rejection_message = (
                f"Action '{tool_name}' was blocked by safety policy. "
                f"Reason: {decision.rejection_reason}. "
                f"Risk score: {decision.risk_score.value:.2f}. "
                f"Applied policies: {', '.join(decision.applied_policies)}. "
                "Please suggest a safer alternative."
            )

        return GuardedToolCall(
            tool_name=tool_name,
            allowed=decision.allowed,
            safe_input=safe_input,
            original_input=tool_input,
            decision=decision,
            rejection_message=rejection_message,
        )

    def check_tool_calls_batch(
        self,
        tool_calls: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[GuardedToolCall]:
        """
        Check a batch of tool calls (e.g. from a parallel tool_use response).
        All calls are evaluated independently.

        Each item in tool_calls must have keys: "name", "input".
        """
        return [
            self.check_tool_call(
                tool_name=tc["name"],
                tool_input=tc.get("input", {}),
                context=context,
            )
            for tc in tool_calls
        ]

    def format_rejection_for_llm(self, result: GuardedToolCall) -> str:
        """
        Format a blocked tool call for re-injection into LLM context.
        Returns a string suitable for a tool_result / function_call_result message.
        """
        if result.allowed:
            return ""
        return (
            f"[SAFETY BLOCK] {result.rejection_message}\n"
            f"Suggested alternative: {result.decision.suggested_alternative or 'reduce speed or change zone'}"
        )
