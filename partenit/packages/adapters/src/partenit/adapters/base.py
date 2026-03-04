"""
RobotAdapter — abstract base class for all robot adapters.

All robot-specific code lives in partenit-adapters.
Core packages have zero knowledge of any robot or simulator.

Vendor contract:
    GET  /partenit/observations  ->  StructuredObservation[]
    POST /partenit/command       <-  GuardDecision
    GET  /partenit/health        ->  {status, robot_id, timestamp}
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from partenit.core.models import GuardDecision, StructuredObservation


class RobotAdapter(ABC):
    """
    Abstract base class for all Partenit robot adapters.

    Implement this to integrate any robot, simulator, or test stub.
    The rest of the Partenit stack (guard, bench, analyzer) only
    calls these four methods.
    """

    @abstractmethod
    def get_observations(self) -> list[StructuredObservation]:
        """
        Fetch the current sensor observations.

        Returns a list of StructuredObservation objects representing
        all detected objects in the scene.
        """
        ...

    @abstractmethod
    def send_decision(self, decision: GuardDecision) -> bool:
        """
        Send a guard decision to the robot.

        Returns True if the command was acknowledged.
        """
        ...

    @abstractmethod
    def get_health(self) -> dict:
        """
        Return adapter / robot health status.

        Expected keys: status (str), robot_id (str), timestamp (str)
        """
        ...

    @abstractmethod
    def is_simulation(self) -> bool:
        """Return True for simulation adapters, False for real hardware."""
        ...
