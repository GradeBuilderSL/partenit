"""
Basic risk scorer for the open-source Partenit guard.

Computes a RiskScore from:
- Minimum distance to any detected human/object
- Requested action speed
- Mean sensor trust level

Advanced plan-conditional risk scoring is enterprise-only.
"""

from __future__ import annotations

from typing import Any

from partenit.core.models import RiskScore, StructuredObservation

_SPEED_PARAM_KEYS = ("speed", "max_velocity", "velocity", "max_speed")


def _extract_speed(params: dict[str, Any]) -> float | None:
    for key in _SPEED_PARAM_KEYS:
        if key in params:
            try:
                return float(params[key])
            except (TypeError, ValueError):
                pass
    return None


def compute_risk(
    action: str,
    params: dict[str, Any],
    context: dict[str, Any],
    observations: list[StructuredObservation] | None = None,
) -> RiskScore:
    """
    Compute a basic RiskScore for a candidate action.

    Args:
        action: Action name (e.g. 'navigate_to')
        params: Action parameters
        context: World-state context dict (e.g. from adapter.get_observations())
        observations: Optional structured observations for distance/trust calc

    Returns:
        RiskScore with value ∈ [0, 1] and contributors breakdown
    """
    contributors: dict[str, float] = {}
    total = 0.0

    # 1. Distance risk — closer objects = higher risk
    distance_risk = _distance_risk(context, observations)
    contributors["distance"] = distance_risk
    total += distance_risk * 0.5  # 50% weight

    # 2. Speed risk — higher speed = higher risk
    speed = _extract_speed(params)
    speed_risk = 0.0
    if speed is not None:
        speed_risk = min(speed / 3.0, 1.0)  # normalize against 3 m/s reference
    contributors["speed"] = speed_risk
    total += speed_risk * 0.3  # 30% weight

    # 3. Sensor trust risk — lower trust = higher risk
    trust_risk = _trust_risk(context, observations)
    contributors["trust"] = trust_risk
    total += trust_risk * 0.2  # 20% weight

    return RiskScore(
        value=min(total, 1.0),
        contributors=contributors,
    )


def _distance_risk(
    context: dict[str, Any],
    observations: list[StructuredObservation] | None,
) -> float:
    """Compute risk based on proximity to detected objects."""
    distances: list[float] = []

    # From structured observations
    if observations:
        for obs in observations:
            d = obs.distance()
            if obs.treat_as_human or obs.class_best == "human":
                distances.append(d * 0.5)  # Humans weighted double
            else:
                distances.append(d)

    # From context dict (e.g. {'human': {'distance': 1.2}})
    human_dist = _nested_get(context, "human.distance")
    if human_dist is not None:
        try:
            distances.append(float(human_dist) * 0.5)  # Human-weighted
        except (TypeError, ValueError):
            pass

    if not distances:
        return 0.0

    min_dist = min(distances)
    # Risk is inversely proportional to distance, capped at 5m
    return max(0.0, 1.0 - min_dist / 5.0)


def _trust_risk(
    context: dict[str, Any],
    observations: list[StructuredObservation] | None,
) -> float:
    """Compute risk from low sensor trust."""
    trust_values: list[float] = []

    if observations:
        for obs in observations:
            trust_values.append(obs.sensor_trust)

    sensor_trust = _nested_get(context, "sensor.trust")
    if sensor_trust is not None:
        try:
            trust_values.append(float(sensor_trust))
        except (TypeError, ValueError):
            pass

    if not trust_values:
        return 0.0

    mean_trust = sum(trust_values) / len(trust_values)
    return 1.0 - mean_trust  # Low trust = high risk


def _nested_get(d: dict[str, Any], path: str) -> Any:
    """Get a value from a nested dict using dot notation."""
    parts = path.split(".")
    value: Any = d
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
        if value is None:
            return None
    return value
