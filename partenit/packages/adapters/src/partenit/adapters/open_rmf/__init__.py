"""
OpenRMFAdapter — adapter stub for Open-RMF (Robotics Middleware Framework).

Open-RMF orchestrates fleets of heterogeneous robots through a common
task dispatch system. This adapter will bridge Open-RMF task events
and robot states into Partenit StructuredObservation, allowing the
safety guard to validate actions before they are dispatched.

Status: STUB — not yet implemented.
Implementation will use the Open-RMF REST API or ROS2 topics.

See: https://github.com/open-rmf/rmf

Architecture intent:
    Open-RMF Task Dispatcher
        ↓ (task request)
    OpenRMFAdapter.get_observations()   ← robot fleet state
        ↓
    AgentGuard.check_action()           ← safety validation
        ↓
    OpenRMFAdapter.send_decision()      ← allow / modify / block task
        ↓
    Open-RMF execution layer
"""
from __future__ import annotations

from partenit.adapters.base import RobotAdapter
from partenit.core.models import GuardDecision, StructuredObservation


class OpenRMFAdapter(RobotAdapter):
    """
    Adapter for Open-RMF robot fleet integration.

    NOT YET IMPLEMENTED. This stub shows the intended interface.
    """

    def __init__(self, rmf_url: str = "http://localhost:8083") -> None:
        self._rmf_url = rmf_url
        raise NotImplementedError(
            "OpenRMFAdapter is not yet implemented. "
            "Use HTTPRobotAdapter with an Open-RMF gateway for now."
        )

    def get_observations(self) -> list[StructuredObservation]:
        raise NotImplementedError

    def send_decision(self, decision: GuardDecision) -> bool:
        raise NotImplementedError

    def get_health(self) -> dict:
        raise NotImplementedError

    def is_simulation(self) -> bool:
        return False
