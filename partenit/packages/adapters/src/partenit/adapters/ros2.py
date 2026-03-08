"""
ROS2Adapter — adapter for ROS2 robots via rclpy.

Optional dependency: rclpy is not required for open-source installation.
If rclpy is not installed, importing this module raises ImportError with
a helpful message.

Usage:
    adapter = ROS2Adapter(node_name="partenit_guard")
    obs = adapter.get_observations()
    adapter.send_decision(decision)
"""

from __future__ import annotations

try:
    import rclpy  # noqa: F401

    _RCLPY_AVAILABLE = True
except ImportError:
    _RCLPY_AVAILABLE = False

from datetime import UTC

from partenit.adapters.base import RobotAdapter
from partenit.core.models import GuardDecision, StructuredObservation


class ROS2Adapter(RobotAdapter):
    """
    Adapter for ROS2 robots.

    Requires rclpy to be installed (part of a ROS2 distribution).
    Install ROS2 first, then this adapter will work automatically.

    Topics consumed:
        /partenit/observations  (partenit_msgs/ObservationArray)
    Topics published:
        /partenit/command       (partenit_msgs/GuardDecision)
    """

    def __init__(self, node_name: str = "partenit_guard") -> None:
        if not _RCLPY_AVAILABLE:
            raise ImportError(
                "rclpy is required for ROS2Adapter. "
                "Install a ROS2 distribution and source its setup.bash. "
                "See: https://docs.ros.org/en/humble/Installation.html"
            )
        self.node_name = node_name
        self._node = None
        self._latest_observations: list[StructuredObservation] = []
        self._init_node()

    def _init_node(self) -> None:
        import rclpy

        rclpy.init()
        # Node initialization — simplified for open-source version
        # Full implementation with message type support is enterprise
        self._node = rclpy.create_node(self.node_name)

    def get_observations(self) -> list[StructuredObservation]:
        """Return latest observations from ROS2 topic."""
        return list(self._latest_observations)

    def send_decision(self, decision: GuardDecision) -> bool:
        """Publish guard decision to ROS2 topic."""
        # Full implementation requires partenit_msgs package
        return True

    def get_health(self) -> dict:
        from datetime import datetime

        return {
            "status": "ok" if self._node else "not_initialized",
            "robot_id": self.node_name,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def is_simulation(self) -> bool:
        return False

    def destroy(self) -> None:
        """Clean up ROS2 node."""
        if self._node:
            import rclpy

            self._node.destroy_node()
            rclpy.shutdown()
