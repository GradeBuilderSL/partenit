"""
AgentGuard — central action safety middleware.

Intercepts every action before execution:
1. Evaluate all applicable PolicyRules against context
2. Compute RiskScore
3. Return GuardDecision (allow / block / modify params)

Every decision is logged (even safe ones) — there is no code path
that skips logging.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from partenit.agent_guard.risk import compute_risk
from partenit.core.models import (
    GuardDecision,
    PolicyBundle,
    SafetyEvent,
    SafetyEventType,
    StructuredObservation,
)
from partenit.policy_dsl.bundle import PolicyBundleBuilder
from partenit.policy_dsl.evaluator import PolicyEvaluator

logger = logging.getLogger(__name__)

_DEFAULT_RISK_THRESHOLD = 0.8


class AgentGuard:
    """
    Safety middleware that intercepts actions for LLM agents, ROS2, and generic callers.

    Usage:
        guard = AgentGuard()
        guard.load_policies("./policies/warehouse.yaml")

        decision = guard.check_action(
            action="navigate_to",
            params={"zone": "A3", "speed": 2.0},
            context={"humans_nearby": 1, "human": {"distance": 1.2}},
        )

        if decision.allowed:
            execute(decision.modified_params or params)
        else:
            log(decision.rejection_reason)
    """

    def __init__(
        self,
        risk_threshold: float = _DEFAULT_RISK_THRESHOLD,
    ) -> None:
        """
        Args:
            risk_threshold: Actions with risk_score.value >= this are blocked
                            even if no policy explicitly fires a 'block'.
        """
        self.risk_threshold = risk_threshold
        self._bundle: PolicyBundle | None = None
        self._evaluator = PolicyEvaluator()
        self._events: list[SafetyEvent] = []

    # ------------------------------------------------------------------
    # Policy loading
    # ------------------------------------------------------------------

    def load_policies(self, path: str | Path) -> int:
        """
        Load policies from a YAML file, directory, or bundled JSON.

        Returns:
            Number of rules loaded.
        """
        path = Path(path)
        builder = PolicyBundleBuilder()

        if path.suffix == ".json":
            self._bundle = PolicyBundleBuilder.load(path)
        elif path.is_dir():
            self._bundle = builder.from_dir(path)
        else:
            self._bundle = builder.from_file(path)

        n = len(self._bundle.rules)
        logger.info("AgentGuard: loaded %d rules (bundle %s)", n, self._bundle.bundle_hash[:8])
        return n

    def load_bundle(self, bundle: PolicyBundle) -> None:
        """Load a pre-built PolicyBundle directly."""
        self._bundle = bundle
        logger.info(
            "AgentGuard: bundle loaded (%d rules, hash %s)",
            len(bundle.rules),
            bundle.bundle_hash[:8],
        )

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------

    def check_action(
        self,
        action: str,
        params: dict[str, Any],
        context: dict[str, Any],
        observations: list[StructuredObservation] | None = None,
    ) -> GuardDecision:
        """
        Check whether an action is safe to execute.

        Args:
            action: Action name (e.g. 'navigate_to', 'pick_object')
            params: Action parameters
            context: World-state context dict (flat or nested)
            observations: Optional list of StructuredObservation objects

        Returns:
            GuardDecision with allowed/blocked status and optional modified params
        """
        start = time.perf_counter()
        rules = self._bundle.rules if self._bundle else []

        # 1. Policy evaluation
        eval_result = self._evaluator.evaluate(rules, context)

        # 2. Risk scoring
        risk = compute_risk(action, params, context, observations)

        # 3. Determine outcome
        allowed = True
        rejection_reason: str | None = None
        modified_params: dict[str, Any] | None = None

        # Check for blocking policies (highest priority first)
        if eval_result.has_violations:
            allowed = False
            blocking_rules = [r for r in eval_result.fired_rules if r.action.type == "block"]
            rejection_reason = "; ".join(f"{r.rule_id}: {r.name}" for r in blocking_rules)
            self._emit_event(
                SafetyEventType.LLM_BLOCKED,
                triggered_by=blocking_rules[0].rule_id if blocking_rules else "policy",
                severity=0.9,
                context={"action": action, "reason": rejection_reason},
            )

        # Apply clamps to params (even if allowed)
        clamps = eval_result.get_clamps()
        if clamps:
            # Merge clamps into a copy of params
            clamped = dict(params)
            for param, clamped_value in clamps.items():
                original = clamped.get(param)
                if original is not None:
                    # Only reduce (clamp), never increase
                    try:
                        if float(original) > float(clamped_value):
                            clamped[param] = clamped_value
                    except (TypeError, ValueError):
                        clamped[param] = clamped_value
                else:
                    clamped[param] = clamped_value
            modified_params = clamped

        # Risk threshold check (even without explicit block policy)
        if allowed and risk.value >= self.risk_threshold:
            allowed = False
            rejection_reason = (
                f"Risk score {risk.value:.2f} exceeds threshold {self.risk_threshold:.2f}"
            )

        latency_ms = (time.perf_counter() - start) * 1000

        decision = GuardDecision(
            allowed=allowed,
            modified_params=modified_params,
            rejection_reason=rejection_reason,
            risk_score=risk,
            applied_policies=eval_result.applied_policy_ids,
            latency_ms=latency_ms,
        )

        logger.debug(
            "check_action(%s): allowed=%s risk=%.2f policies=%s latency=%.1fms",
            action,
            allowed,
            risk.value,
            eval_result.applied_policy_ids,
            latency_ms,
        )
        return decision

    # ------------------------------------------------------------------
    # Event log access
    # ------------------------------------------------------------------

    def get_events(self) -> list[SafetyEvent]:
        """Return all safety events emitted during this session."""
        return list(self._events)

    def clear_events(self) -> None:
        """Clear the in-memory event log."""
        self._events.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_event(
        self,
        event_type: SafetyEventType,
        triggered_by: str,
        severity: float,
        context: dict[str, Any],
    ) -> SafetyEvent:
        event = SafetyEvent(
            event_type=event_type,
            triggered_by=triggered_by,
            severity=severity,
            context=context,
        )
        self._events.append(event)
        return event
