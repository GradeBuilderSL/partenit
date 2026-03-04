"""
MockRobotAdapter — simulation adapter, no hardware required.

Generates deterministic, configurable sensor observations for
testing, safety benchmarking, and development.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from typing import Any

from partenit.core.models import GuardDecision, StructuredObservation
from partenit.adapters.base import RobotAdapter


class MockRobotAdapter(RobotAdapter):
    """
    Simulation adapter that generates configurable observations.

    Usage:
        adapter = MockRobotAdapter()
        obs = adapter.get_observations()   # scene with random objects

        # Configure scene
        adapter.set_scene([
            {"object_id": "h1", "class_best": "human", "position_3d": (1.2, 0, 0)},
        ])
    """

    def __init__(
        self,
        robot_id: str = "mock-robot-0",
        seed: int | None = None,
    ) -> None:
        self.robot_id = robot_id
        self._rng = random.Random(seed)
        self._scene: list[dict[str, Any]] = []
        self._sent_decisions: list[GuardDecision] = []
        self._healthy = True

    def set_scene(self, objects: list[dict[str, Any]]) -> None:
        """
        Configure the scene for the next get_observations() call.

        Each dict may contain fields matching StructuredObservation.
        Minimum required: object_id, class_best, position_3d.
        """
        self._scene = objects

    def add_human(self, object_id: str, x: float, y: float, z: float = 0.0) -> None:
        """Convenience: add a human detection to the scene."""
        self._scene.append({
            "object_id": object_id,
            "class_best": "human",
            "class_set": ["human"],
            "position_3d": (x, y, z),
            "confidence": 0.92,
            "sensor_trust": 1.0,
        })

    def add_object(
        self,
        object_id: str,
        class_label: str,
        x: float,
        y: float,
        z: float = 0.0,
        confidence: float = 0.85,
    ) -> None:
        """Convenience: add any object to the scene."""
        self._scene.append({
            "object_id": object_id,
            "class_best": class_label,
            "class_set": [class_label],
            "position_3d": (x, y, z),
            "confidence": confidence,
            "sensor_trust": 1.0,
        })

    def clear_scene(self) -> None:
        """Remove all objects from the scene."""
        self._scene.clear()

    def get_observations(self) -> list[StructuredObservation]:
        """Return current scene as StructuredObservation list."""
        obs: list[StructuredObservation] = []
        now = datetime.now(timezone.utc)
        for item in self._scene:
            data = {
                "object_id": item.get("object_id", "obj-0"),
                "class_best": item.get("class_best", "unknown"),
                "class_set": item.get("class_set", [item.get("class_best", "unknown")]),
                "position_3d": item.get("position_3d", (5.0, 0.0, 0.0)),
                "velocity": item.get("velocity", (0.0, 0.0, 0.0)),
                "confidence": item.get("confidence", 0.9),
                "depth_variance": item.get("depth_variance", 0.01),
                "sensor_trust": item.get("sensor_trust", 1.0),
                "timestamp": now,
                "frame_hash": self._hash_item(item),
                "source_id": item.get("source_id", "mock-cam-0"),
            }
            obs.append(StructuredObservation.model_validate(data))
        return obs

    def send_decision(self, decision: GuardDecision) -> bool:
        """Record the decision (simulation only — no actual command sent)."""
        self._sent_decisions.append(decision)
        return True

    def get_health(self) -> dict:
        return {
            "status": "ok" if self._healthy else "degraded",
            "robot_id": self.robot_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_simulation": True,
        }

    def is_simulation(self) -> bool:
        return True

    @property
    def decisions_sent(self) -> list[GuardDecision]:
        """Return all decisions sent during this session."""
        return list(self._sent_decisions)

    def _hash_item(self, item: dict[str, Any]) -> str:
        content = json.dumps(item, default=str, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
