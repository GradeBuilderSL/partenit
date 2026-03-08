"""
ObjectConfidenceModel — models per-object confidence decay over time.

Formula:
    confidence(t) = confidence(t0) * exp(-lambda * time_since_seen)

lambda is configurable per object class. Humans decay faster than furniture
because their position is more uncertain over time.

Below threshold 0.1 → mark as location_uncertain.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

_DEFAULT_LAMBDAS: dict[str, float] = {
    "human": 0.5,        # Humans move — decay fast (half-life ~2s)
    "person": 0.5,
    "robot": 0.2,        # Robots are slower
    "forklift": 0.15,
    "vehicle": 0.15,
    "obstacle": 0.05,    # Static obstacles decay slowly
    "box": 0.03,
    "shelf": 0.01,
    "wall": 0.005,
    "default": 0.1,
}

_LOCATION_UNCERTAIN_THRESHOLD = 0.1


class TrackedObject:
    """Tracks one object's confidence decay."""

    def __init__(
        self,
        object_id: str,
        class_label: str,
        initial_confidence: float,
        lambda_override: float | None = None,
    ) -> None:
        self.object_id = object_id
        self.class_label = class_label
        self._initial_confidence = initial_confidence
        self._last_seen: datetime = datetime.now(UTC)
        self._lambda = lambda_override or _DEFAULT_LAMBDAS.get(
            class_label, _DEFAULT_LAMBDAS["default"]
        )

    def observe(self, confidence: float) -> None:
        """Update with a fresh detection. Resets decay clock."""
        self._initial_confidence = confidence
        self._last_seen = datetime.now(UTC)

    def confidence_at(self, t: datetime | None = None) -> float:
        """Compute decayed confidence at time t (default: now)."""
        if t is None:
            t = datetime.now(UTC)
        elapsed = (t - self._last_seen).total_seconds()
        elapsed = max(elapsed, 0.0)
        return self._initial_confidence * math.exp(-self._lambda * elapsed)

    @property
    def location_uncertain(self) -> bool:
        return self.confidence_at() < _LOCATION_UNCERTAIN_THRESHOLD

    @property
    def seconds_since_seen(self) -> float:
        return (datetime.now(UTC) - self._last_seen).total_seconds()


class ObjectConfidenceModel:
    """
    Maintains per-object confidence for all tracked objects in the scene.

    Usage:
        model = ObjectConfidenceModel()
        model.observe("obj-1", "human", confidence=0.9)
        # ... time passes ...
        conf = model.confidence("obj-1")       # decayed value
        uncertain = model.is_uncertain("obj-1")
    """

    def __init__(
        self,
        lambda_overrides: dict[str, float] | None = None,
    ) -> None:
        """
        Args:
            lambda_overrides: Per-class lambda values to override defaults.
                e.g. {"human": 0.3} to make humans decay slower.
        """
        self._objects: dict[str, TrackedObject] = {}
        self._lambda_overrides = lambda_overrides or {}

    def observe(
        self,
        object_id: str,
        class_label: str,
        confidence: float,
    ) -> None:
        """Record a fresh detection for an object."""
        if object_id not in self._objects:
            lam = self._lambda_overrides.get(
                class_label, _DEFAULT_LAMBDAS.get(class_label, _DEFAULT_LAMBDAS["default"])
            )
            self._objects[object_id] = TrackedObject(
                object_id=object_id,
                class_label=class_label,
                initial_confidence=confidence,
                lambda_override=lam,
            )
        else:
            self._objects[object_id].observe(confidence)

    def confidence(self, object_id: str) -> float | None:
        """Return current decayed confidence, or None if object unknown."""
        obj = self._objects.get(object_id)
        if obj is None:
            return None
        return obj.confidence_at()

    def is_uncertain(self, object_id: str) -> bool:
        """Return True if object's location is uncertain (confidence < 0.1)."""
        obj = self._objects.get(object_id)
        if obj is None:
            return True
        return obj.location_uncertain

    def prune(self, max_age_seconds: float = 60.0) -> list[str]:
        """
        Remove objects not seen for longer than max_age_seconds.
        Returns list of pruned object_ids.
        """
        stale = [
            oid for oid, obj in self._objects.items()
            if obj.seconds_since_seen > max_age_seconds
        ]
        for oid in stale:
            del self._objects[oid]
        return stale

    def all_states(self) -> dict[str, dict]:
        """Return current state for all tracked objects."""
        return {
            oid: {
                "confidence": obj.confidence_at(),
                "class": obj.class_label,
                "location_uncertain": obj.location_uncertain,
                "seconds_since_seen": obj.seconds_since_seen,
            }
            for oid, obj in self._objects.items()
        }
