"""
UnitreeAdapter — thin wrapper around ROS2Adapter for Unitree robots.

This adapter adds **no Unitree-specific safety logic**. It only maps
Unitree-specific ROS2 message fields into the generic Partenit
`StructuredObservation` model where necessary.

NOTE: The open-source version keeps this mapping minimal and does not
depend on proprietary Unitree SDKs. Full message support can be added
in enterprise or project-specific layers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from partenit.adapters.ros2 import ROS2Adapter


class UnitreeAdapter(ROS2Adapter):
    """
    Adapter for Unitree robots that already expose their state via ROS2.

    The adapter relies entirely on ROS2 topics and the base `ROS2Adapter`
    implementation for transport. Any robot-specific field mapping is
    purely mechanical (no safety decisions here).
    """

    def __init__(self, node_name: str = "partenit_unitree") -> None:
        super().__init__(node_name=node_name)

    # In a full implementation we would override subscription callbacks
    # to decode Unitree messages into StructuredObservation. In the open
    # version we keep this as a direct passthrough to the base class.

    def get_health(self) -> dict[str, Any]:
        base = super().get_health()
        base.setdefault("timestamp", datetime.now(UTC).isoformat())
        base.setdefault("vendor", "unitree")
        return base

