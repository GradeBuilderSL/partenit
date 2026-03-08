"""
Guard decorator for wrapping Python functions with action safety checks.

Usage:
    guard = AgentGuard()
    guard.load_policies("./policies/")

    @guard_action(guard, action_name="navigate_to", context_key="world_state")
    def navigate_to(zone: str, speed: float, world_state: dict) -> bool:
        ...  # Only called if guard allows
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any

from partenit.agent_guard.core import AgentGuard

logger = logging.getLogger(__name__)


def guard_action(
    guard: AgentGuard,
    action_name: str | None = None,
    context_key: str = "context",
    risk_threshold: float | None = None,
) -> Callable:
    """
    Decorator factory that wraps a function with a guard check.

    The decorated function receives the guard decision as a kwarg
    `guard_decision` and is only called if the decision allows execution.

    Args:
        guard: The AgentGuard instance to use.
        action_name: Override action name (defaults to function name).
        context_key: The kwarg name that holds the context dict.
        risk_threshold: Override risk threshold for this specific action.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            name = action_name or fn.__name__

            # Extract params from kwargs (everything except context_key)
            params = {k: v for k, v in kwargs.items() if k != context_key}
            context = kwargs.get(context_key, {})

            # Apply risk threshold override
            original_threshold = guard.risk_threshold
            if risk_threshold is not None:
                guard.risk_threshold = risk_threshold

            decision = guard.check_action(
                action=name,
                params=params,
                context=context,
            )

            if risk_threshold is not None:
                guard.risk_threshold = original_threshold

            if not decision.allowed:
                logger.warning(
                    "Guard blocked '%s': %s", name, decision.rejection_reason
                )
                return decision

            # Pass modified params back to function
            if decision.modified_params:
                kwargs.update(decision.modified_params)

            return fn(*args, **kwargs)

        return wrapper

    return decorator
