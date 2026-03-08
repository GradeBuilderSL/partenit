"""
GuardedRobot — 1-line high-level robot wrapper.

Combines adapter + guard + optional logger so the developer never
touches AgentGuard, DecisionLogger, or observations directly.

Usage (minimal):
    robot = GuardedRobot(adapter)
    robot.navigate_to(zone="shipping", speed=2.0)

Usage (full):
    robot = GuardedRobot(
        adapter=MockRobotAdapter(),
        policy_path="policies/warehouse.yaml",
        session_name="warehouse_test",
    )
    decision = robot.navigate_to(zone="shipping", speed=2.0)
    print(decision.allowed, decision.risk_score.value)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from partenit.agent_guard.core import AgentGuard
from partenit.core.models import GuardDecision, SafetyEvent

logger = logging.getLogger(__name__)

# Optional import — decision-log is not a hard dep of agent-guard
try:
    from partenit.decision_log import DecisionLogger as _DecisionLogger  # type: ignore[import]

    _HAS_DECISION_LOG = True
except ImportError:
    _HAS_DECISION_LOG = False
    _DecisionLogger = None  # type: ignore[assignment]


class GuardedRobot:
    """
    High-level robot wrapper: adapter + guard + logging in one object.

    The adapter is duck-typed — any object with ``get_observations()``
    and ``send_decision()`` methods works.  This avoids a circular import
    between ``partenit-agent-guard`` and ``partenit-adapters``.

    Args:
        adapter:          Robot adapter (MockRobotAdapter, HTTPRobotAdapter, …).
        policy_path:      Path to YAML policies or directory.  Optional.
        session_name:     Session label for decision recording.  When provided
                          and ``partenit-decision-log`` is installed, decisions
                          are stored in ``decisions/<session_name>/``.
        risk_threshold:   Risk score threshold above which actions are blocked.
    """

    def __init__(
        self,
        adapter: Any,
        policy_path: str | Path | None = None,
        session_name: str | None = None,
        risk_threshold: float = 0.8,
    ) -> None:
        self._adapter = adapter
        self._guard = AgentGuard(risk_threshold=risk_threshold)
        if policy_path is not None:
            self._guard.load_policies(Path(policy_path))

        self._logger: Any | None = None
        if _HAS_DECISION_LOG and _DecisionLogger is not None:
            storage_dir = f"decisions/{session_name}" if session_name else None
            self._logger = _DecisionLogger(storage_dir=storage_dir)

        self._last_decision: GuardDecision | None = None
        self._session_name = session_name

    # ------------------------------------------------------------------
    # Public action API
    # ------------------------------------------------------------------

    def execute_action(self, action: str, **params: Any) -> GuardDecision:
        """
        Execute any action through the guard.

        Steps:
        1. Get observations from adapter
        2. Build context dict from observations
        3. Run guard check (policies + risk)
        4. If allowed: send decision to adapter (with modified params)
        5. Log decision (always, even on block)
        6. Return GuardDecision

        Args:
            action:    Action name (e.g. "navigate_to", "pick_up").
            **params:  Action parameters.

        Returns:
            GuardDecision with allowed/blocked status.
        """
        # 1. Get observations (duck-typed call)
        try:
            observations = self._adapter.get_observations()
        except Exception as exc:
            logger.warning("GuardedRobot: get_observations() failed: %s", exc)
            observations = []

        # 2. Build context dict
        context = _build_context(observations)

        # 3. Guard check
        decision = self._guard.check_action(
            action=action,
            params=params,
            context=context,
            observations=observations,
        )

        # 4. Always send decision (allow → apply params; block → adapter sets stop).
        # Adapters must get BLOCKED so they set cmd_vel=0; else robot keeps last cmd.
        try:
            effective = decision
            if decision.allowed and decision.modified_params is None:
                effective = decision.model_copy(update={"modified_params": dict(params)})
            self._adapter.send_decision(effective)
        except Exception as exc:
            logger.warning("GuardedRobot: send_decision() failed: %s", exc)

        # 5. Log decision
        if self._logger is not None:
            try:
                self._logger.create_packet(
                    action_requested=action,
                    action_params=params,
                    guard_decision=decision,
                )
            except Exception as exc:
                logger.warning("GuardedRobot: decision logging failed: %s", exc)

        self._last_decision = decision
        return decision

    def navigate_to(
        self,
        zone: str,
        speed: float = 1.0,
        **kwargs: Any,
    ) -> GuardDecision:
        """Navigate to zone at given speed. Guard may clamp speed or block."""
        return self.execute_action("navigate_to", zone=zone, speed=speed, **kwargs)

    def pick_up(self, target: str, **kwargs: Any) -> GuardDecision:
        """Pick up object. Guard checks safety before execution."""
        return self.execute_action("pick_up", target=target, **kwargs)

    def move_to(self, x: float, y: float, speed: float = 1.0, **kwargs: Any) -> GuardDecision:
        """Move to coordinates. Guard may clamp speed or block."""
        return self.execute_action("move_to", x=x, y=y, speed=speed, **kwargs)

    def stop(self) -> None:
        """Emergency stop — sends block decision directly to adapter."""
        from partenit.core.models import RiskScore

        decision = GuardDecision(
            allowed=False,
            rejection_reason="manual_stop",
            risk_score=RiskScore(value=0.0, features={}),
            applied_policies=[],
        )
        try:
            self._adapter.send_decision(decision)
        except Exception as exc:
            logger.warning("GuardedRobot: stop send_decision() failed: %s", exc)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def last_decision(self) -> GuardDecision | None:
        """Most recent GuardDecision returned by execute_action."""
        return self._last_decision

    @property
    def risk_score(self) -> float | None:
        """Risk score from the most recent decision (0.0–1.0)."""
        if self._last_decision and self._last_decision.risk_score:
            return self._last_decision.risk_score.value
        return None

    @property
    def events(self) -> list[SafetyEvent]:
        """Safety events recorded by the guard in this session."""
        return self._guard.get_events()

    @property
    def session_name(self) -> str | None:
        """Session name used for decision recording."""
        return self._session_name

    def __repr__(self) -> str:
        adapter_name = type(self._adapter).__name__
        policies = len(self._guard._bundle.rules) if self._guard._bundle else 0
        return (
            f"GuardedRobot(adapter={adapter_name}, "
            f"policies={policies}, "
            f"session={self._session_name!r})"
        )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _build_context(observations: list[Any]) -> dict[str, Any]:
    """
    Build a context dict from a list of StructuredObservation objects.

    Extracts the nearest human (if any) for the guard to evaluate
    proximity-based policies.
    """
    context: dict[str, Any] = {}
    nearest_dist = float("inf")
    nearest_human: Any | None = None

    for obs in observations:
        # Duck-typed access — works with StructuredObservation and any mock
        treat_as_human = getattr(obs, "treat_as_human", False)
        class_best = getattr(obs, "class_best", "") or ""
        class_set = getattr(obs, "class_set", []) or []
        is_human = (
            treat_as_human
            or "human" in class_best.lower()
            or "person" in class_best.lower()
            or any("human" in c.lower() or "person" in c.lower() for c in class_set)
        )

        # StructuredObservation.distance() is a method; also support position_3d tuple
        distance: float | None = None
        dist_method = getattr(obs, "distance", None)
        if callable(dist_method):
            try:
                distance = float(dist_method())
            except Exception:
                pass
        if distance is None:
            pos = getattr(obs, "position_3d", None)
            if isinstance(pos, (tuple, list)) and len(pos) >= 2:
                distance = float(
                    (pos[0] ** 2 + pos[1] ** 2 + (pos[2] if len(pos) > 2 else 0.0) ** 2) ** 0.5
                )
        if distance is None:
            x = getattr(obs, "x", None)
            y = getattr(obs, "y", None)
            if x is not None and y is not None:
                distance = float((x**2 + y**2) ** 0.5)

        if is_human and distance is not None and distance < nearest_dist:
            nearest_dist = distance
            nearest_human = obs

    if nearest_human is not None:
        confidence = getattr(nearest_human, "confidence", 1.0)
        sensor_trust = getattr(nearest_human, "sensor_trust", 1.0)
        context["human"] = {
            "distance": nearest_dist,
            "id": getattr(nearest_human, "object_id", "human"),
            "confidence": confidence,
            "sensor_trust": sensor_trust,
        }

    return context
