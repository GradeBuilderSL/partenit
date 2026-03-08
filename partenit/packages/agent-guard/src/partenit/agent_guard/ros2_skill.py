"""
ROS2SkillGuard — guard wrapper for ROS2 action client calls.

Intercepts ROS2 action goals before they are sent to the action server.
Does NOT depend on rclpy — usable in any environment.

Usage:
    guard = AgentGuard()
    guard.load_policies("./policies/")

    ros2_guard = ROS2SkillGuard(guard)

    # Before sending a goal to e.g. NavigateToPose:
    decision = ros2_guard.check_goal(
        action_name="navigate_to_pose",
        goal={"pose": {"x": 5.0, "y": 0.0}, "speed": 2.5},
        context={"human": {"distance": 1.2}},
    )
    if decision.allowed:
        # send goal, possibly with modified params from decision.modified_params
        goal_to_send = decision.modified_params or goal
        action_client.send_goal(goal_to_send)
    else:
        logger.warning("Goal blocked: %s", decision.rejection_reason)

Integration with real ROS2:
    The caller is responsible for converting ROS2 message objects to dicts
    before passing them to check_goal(). This keeps ROS2SkillGuard dependency-free.

    Example with nav2:
        goal_dict = {
            "pose": {"x": msg.pose.pose.position.x,
                     "y": msg.pose.pose.position.y},
            "speed": msg.speed,
        }
        decision = ros2_guard.check_goal("navigate_to_pose", goal_dict, context)
"""

from __future__ import annotations

import logging
from typing import Any

from partenit.agent_guard.core import AgentGuard
from partenit.core.models import GuardDecision

logger = logging.getLogger(__name__)


class ROS2SkillGuard:
    """
    Guard wrapper for ROS2 action-client calls.

    Intercepts action goals before they reach the ROS2 action server.
    Dependency-free: does not import rclpy. The caller converts ROS2
    message objects to plain dicts.

    Args:
        guard: The AgentGuard instance to use for policy evaluation.
    """

    def __init__(self, guard: AgentGuard) -> None:
        self._guard = guard

    def check_goal(
        self,
        action_name: str,
        goal: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> GuardDecision:
        """
        Check an action goal before sending it to the ROS2 action server.

        Args:
            action_name: ROS2 action name (e.g. "navigate_to_pose", "dock").
            goal: Goal fields as a plain dict (convert from ROS2 msg first).
            context: World context (humans, obstacles, sensor state, etc.).

        Returns:
            GuardDecision — check `.allowed` before sending the goal.
            If `.modified_params` is set, use those values instead of the
            original goal fields (e.g. clamped speed).
        """
        decision = self._guard.check_action(
            action=action_name,
            params=goal,
            context=context or {},
        )
        if not decision.allowed:
            logger.warning(
                "ROS2SkillGuard blocked '%s': %s", action_name, decision.rejection_reason
            )
        elif decision.modified_params:
            logger.info(
                "ROS2SkillGuard modified '%s' params: %s", action_name, decision.modified_params
            )
        return decision

    def check_service(
        self,
        service_name: str,
        request: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> GuardDecision:
        """
        Check a ROS2 service request before calling the service.

        Same semantics as check_goal but for service calls.
        """
        return self.check_goal(service_name, request, context)
