"""
MockWorld — simulated environment for safety benchmarking.

Maintains a list of objects in the world and produces StructuredObservations
at each simulation tick.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class WorldObject:
    """An object in the simulated world."""

    object_id: str
    class_label: str
    x: float
    y: float
    z: float = 0.0
    vx: float = 0.0  # velocity m/s
    vy: float = 0.0
    confidence: float = 0.9
    sensor_trust: float = 1.0
    appears_at: float = 0.0  # simulation time when object enters scene

    def distance_to(self, rx: float, ry: float) -> float:
        return math.sqrt((self.x - rx) ** 2 + (self.y - ry) ** 2)


class MockWorld:
    """
    Simulated world that steps forward in time.

    Objects move according to their velocity.
    The robot position is tracked separately.

    Sensor trust degradation:
        Use set_trust_profile() to configure global trust over time.
        Trust is linearly interpolated between profile points.
        Effective observation trust = object.sensor_trust * global_trust.
    """

    def __init__(self) -> None:
        self._objects: list[WorldObject] = []
        self._robot_x: float = 0.0
        self._robot_y: float = 0.0
        self._time: float = 0.0
        # Each entry: (at_time, trust_value), sorted by time
        self._trust_profile: list[tuple[float, float]] = []

    def add_object(self, obj: WorldObject) -> None:
        self._objects.append(obj)

    def set_robot_position(self, x: float, y: float) -> None:
        self._robot_x = x
        self._robot_y = y

    def set_trust_profile(self, points: list[dict]) -> None:
        """
        Configure global sensor trust degradation profile.

        Args:
            points: List of {at_time: float, trust: float} dicts, any order.

        Example:
            world.set_trust_profile([
                {"at_time": 0.0, "trust": 0.95},
                {"at_time": 5.0, "trust": 0.30},
            ])
        """
        self._trust_profile = sorted(
            [(float(p["at_time"]), float(p["trust"])) for p in points],
            key=lambda x: x[0],
        )

    def get_global_sensor_trust(self) -> float:
        """
        Return global sensor trust at current simulation time.

        Linearly interpolates between profile points.
        Returns 1.0 if no profile is configured.
        """
        if not self._trust_profile:
            return 1.0
        t = self._time
        if t <= self._trust_profile[0][0]:
            return self._trust_profile[0][1]
        if t >= self._trust_profile[-1][0]:
            return self._trust_profile[-1][1]
        for i in range(len(self._trust_profile) - 1):
            t0, v0 = self._trust_profile[i]
            t1, v1 = self._trust_profile[i + 1]
            if t0 <= t <= t1:
                frac = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                return v0 + frac * (v1 - v0)
        return self._trust_profile[-1][1]

    def step(self, dt: float) -> None:
        """Advance simulation by dt seconds."""
        self._time += dt
        for obj in self._objects:
            obj.x += obj.vx * dt
            obj.y += obj.vy * dt

    @property
    def time(self) -> float:
        return self._time

    def get_context(self) -> dict:
        """
        Return current world state as a context dict for policy evaluation.

        Finds the nearest visible human and exposes:
          human.distance     — Euclidean distance to nearest human
          human.id           — object_id of nearest human
          human.sensor_trust — effective trust (object trust × global trust)
          human.confidence   — trust-weighted detection confidence
          sensor_trust       — global sensor trust at current time
        """
        global_trust = self.get_global_sensor_trust()
        visible = [o for o in self._objects if self._time >= o.appears_at]
        humans = [o for o in visible if o.class_label in ("human", "person")]

        context: dict = {"sensor_trust": global_trust}
        if humans:
            nearest = min(humans, key=lambda h: h.distance_to(self._robot_x, self._robot_y))
            dist = nearest.distance_to(self._robot_x, self._robot_y)
            eff_trust = min(1.0, nearest.sensor_trust * global_trust)
            context["human"] = {
                "distance": dist,
                "id": nearest.object_id,
                "sensor_trust": eff_trust,
                "confidence": min(1.0, nearest.confidence * eff_trust),
            }

        return context

    def get_observations(self):
        """Return StructuredObservation objects for all visible world objects."""
        from partenit.core.models import StructuredObservation

        global_trust = self.get_global_sensor_trust()
        visible = [o for o in self._objects if self._time >= o.appears_at]
        obs = []
        for obj in visible:
            eff_trust = min(1.0, obj.sensor_trust * global_trust)
            obs.append(StructuredObservation(
                object_id=obj.object_id,
                class_best=obj.class_label,
                class_set=[obj.class_label] + (["human"] if obj.class_label == "person" else []),
                position_3d=(
                    obj.x - self._robot_x,
                    obj.y - self._robot_y,
                    obj.z,
                ),
                velocity=(obj.vx, obj.vy, 0.0),
                confidence=obj.confidence,
                sensor_trust=eff_trust,
            ))
        return obs
