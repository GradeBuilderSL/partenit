"""
MoveItAdapter — adapter stub for MoveIt 2 motion planning.

MoveIt 2 is the standard ROS2 motion planning framework.
This adapter will bridge MoveIt planning requests into Partenit,
allowing the safety guard to validate planned trajectories before
execution — checking for proximity violations, velocity limits, etc.

Status: STUB — not yet implemented.
Implementation requires rclpy + MoveIt2 Python bindings.

Architecture intent:
    MoveIt2 PlanningScene + MotionPlan
        ↓
    MoveItAdapter.get_observations()    ← objects in planning scene
        ↓
    AgentGuard.check_action()           ← validate planned motion
        ↓
    MoveItAdapter.send_decision()       ← allow / modify / block trajectory
        ↓
    MoveIt execution pipeline
"""

from __future__ import annotations

from partenit.adapters.base import RobotAdapter
from partenit.core.models import GuardDecision, StructuredObservation


class MoveItAdapter(RobotAdapter):
    """
    Adapter for MoveIt 2 motion planning integration.

    NOT YET IMPLEMENTED. This stub shows the intended interface.
    """

    def __init__(self, node_name: str = "partenit_moveit") -> None:
        self._node_name = node_name
        raise NotImplementedError(
            "MoveItAdapter is not yet implemented. Use ROS2Adapter for general ROS2 integration."
        )

    def get_observations(self) -> list[StructuredObservation]:
        raise NotImplementedError

    def send_decision(self, decision: GuardDecision) -> bool:
        raise NotImplementedError

    def get_health(self) -> dict:
        raise NotImplementedError

    def is_simulation(self) -> bool:
        return False
