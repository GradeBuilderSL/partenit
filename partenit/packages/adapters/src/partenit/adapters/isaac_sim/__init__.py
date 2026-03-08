"""
IsaacSimAdapter — simulation adapter for NVIDIA Isaac Sim.

This open-source implementation focuses on the **HTTP bridge mode**:
Isaac Sim (or a thin extension inside it) exposes the standard
Partenit HTTP robot API, and this adapter simply wraps `HTTPRobotAdapter`.

This keeps all safety and policy logic out of the adapter and inside
the Partenit core packages, as required by the architecture.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from partenit.adapters.base import RobotAdapter
from partenit.adapters.http import HTTPRobotAdapter
from partenit.core.models import GuardDecision, StructuredObservation


class IsaacSimAdapter(RobotAdapter):
    """
    Adapter for robots simulated in NVIDIA Isaac Sim.

    In this open implementation the adapter does **not** talk to Isaac
    APIs directly. Instead, it expects an HTTP gateway running next to
    the simulator that implements the standard Partenit HTTP contract:

        GET  /partenit/observations  -> StructuredObservation[]
        POST /partenit/command       <- GuardDecision
        GET  /partenit/health        -> {status, robot_id, timestamp}

    That HTTP gateway can be:
    - a small Isaac Sim extension
    - a separate process reading from sim topics and exposing HTTP

    This keeps the adapter thin and reusable while remaining fully
    compatible with the core Partenit stack.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:7000",
        *,
        robot_id: str = "isaac-sim-robot",
        timeout: float = 2.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Args:
            base_url: Base URL of the Isaac Sim HTTP gateway.
            robot_id: Logical identifier for the simulated robot.
            timeout: HTTP timeout in seconds.
            headers: Optional HTTP headers (e.g. auth).
        """
        self._robot_id = robot_id
        # Composition: reuse HTTPRobotAdapter for the actual HTTP work.
        self._http = HTTPRobotAdapter(base_url=base_url, timeout=timeout, headers=headers)

    # ------------------------------------------------------------------
    # RobotAdapter interface
    # ------------------------------------------------------------------

    def get_observations(self) -> list[StructuredObservation]:
        return self._http.get_observations()

    def send_decision(self, decision: GuardDecision) -> bool:
        return self._http.send_decision(decision)

    def get_health(self) -> dict[str, Any]:
        # Prefer the HTTP health endpoint if available; fall back to a
        # minimal, clearly-marked simulation status.
        health = self._http.get_health()
        if "status" not in health:
            health["status"] = "ok"
        if "robot_id" not in health:
            health["robot_id"] = self._robot_id
        if "timestamp" not in health:
            health["timestamp"] = datetime.now(UTC).isoformat()
        health["is_simulation"] = True
        return health

    def is_simulation(self) -> bool:  # pragma: no cover - trivial
        return True

    # ------------------------------------------------------------------
    # Resource management
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close underlying HTTP resources."""
        self._http.close()

    def __enter__(self) -> IsaacSimAdapter:  # pragma: no cover - trivial
        return self

    def __exit__(self, *_: object) -> None:  # pragma: no cover - trivial
        self.close()

