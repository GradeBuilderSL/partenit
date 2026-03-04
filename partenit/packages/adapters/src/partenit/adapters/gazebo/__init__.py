"""
GazeboAdapter — simulation adapter for Gazebo (Classic and Gz/Ignition).

This open-source implementation uses the **HTTP gateway mode**:
a thin bridge process runs alongside the Gazebo simulation and exposes
the standard Partenit HTTP robot API.

The same three-endpoint contract as IsaacSimAdapter and HTTPRobotAdapter:
    GET  /partenit/observations  -> StructuredObservation[]
    POST /partenit/command       <- GuardDecision
    GET  /partenit/health        -> {status, robot_id, timestamp}

The bridge can be implemented as:
- A ROS2 node (if using Gazebo via ROS2) — then use ROS2Adapter instead
- A standalone Python process using gazebo_msgs or gz-msgs
- A generic REST bridge using the robot_adapter_api.yaml contract

This keeps all safety and policy logic out of the adapter and inside
the Partenit core packages, as required by the architecture.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from partenit.adapters.base import RobotAdapter
from partenit.adapters.http import HTTPRobotAdapter
from partenit.core.models import GuardDecision, StructuredObservation


class GazeboAdapter(RobotAdapter):
    """
    Adapter for robots simulated in Gazebo (Classic or Gz/Ignition).

    Expects an HTTP gateway running alongside the simulation that
    implements the standard Partenit HTTP contract.

    Gateway options:
    - ROS2 path: use ROS2Adapter if your Gazebo setup publishes to ROS2 topics.
    - HTTP path: run a small bridge process that reads Gazebo state and
      exposes /partenit/observations, /partenit/command, /partenit/health.

    Usage:
        adapter = GazeboAdapter(base_url="http://localhost:7001")
        obs = adapter.get_observations()
        adapter.send_decision(decision)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:7001",
        *,
        robot_id: str = "gazebo-robot",
        timeout: float = 2.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Args:
            base_url: Base URL of the Gazebo HTTP gateway.
            robot_id: Logical identifier for the simulated robot.
            timeout: HTTP timeout in seconds.
            headers: Optional HTTP headers.
        """
        self._robot_id = robot_id
        self._http = HTTPRobotAdapter(base_url=base_url, timeout=timeout, headers=headers)

    def get_observations(self) -> list[StructuredObservation]:
        return self._http.get_observations()

    def send_decision(self, decision: GuardDecision) -> bool:
        return self._http.send_decision(decision)

    def get_health(self) -> dict[str, Any]:
        health = self._http.get_health()
        health.setdefault("status", "ok")
        health.setdefault("robot_id", self._robot_id)
        health.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        health["is_simulation"] = True
        health["simulator"] = "gazebo"
        return health

    def is_simulation(self) -> bool:
        return True

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "GazeboAdapter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
