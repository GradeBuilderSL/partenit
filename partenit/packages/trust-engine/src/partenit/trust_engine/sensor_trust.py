"""
SensorTrustModel — models sensor trust level over time.

Formula:
    Trust(t+1) = clip(Trust(t) * decay_factor + reinforcement, 0, 1)

where decay_factor < 1 when sensor signals degrade, and reinforcement
is added when signals are consistent.

Degradation triggers (each reduces decay_factor):
- depth_variance_spike: sudden increase in depth noise
- low_lighting: lighting quality below threshold
- inconsistent_detections: repeated class flipping
- noise_spikes: IMU or image noise events
- frame_rate_drops: FPS below minimum threshold
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from partenit.core.models import TrustState


@dataclass
class SensorSignal:
    """
    One sample of sensor quality signals.

    All values are normalized [0, 1] unless noted.
    Higher = worse condition (except frame_rate which is raw FPS).
    """

    depth_variance: float = 0.0          # Normalized depth noise [0, 1]
    lighting_quality: float = 1.0         # 1.0 = perfect, 0.0 = complete darkness
    detection_consistency: float = 1.0    # 1.0 = stable class, 0.0 = constantly flipping
    noise_level: float = 0.0             # General noise [0, 1]
    frame_rate: float = 30.0             # FPS (raw)
    min_frame_rate: float = 15.0         # FPS threshold below which trust degrades


class SensorTrustModel:
    """
    Maintains and updates the trust level of a single sensor.

    Trust represents how reliably we can believe the sensor's output.
    Used by agent-guard to weight observations before policy evaluation.

    Trust thresholds (from CLAUDE.md):
        nominal:    trust > 0.8
        degraded:   0.5 – 0.8
        unreliable: 0.2 – 0.5
        failed:     < 0.2
    """

    def __init__(
        self,
        sensor_id: str,
        initial_trust: float = 1.0,
        decay_rate: float = 0.05,
        recovery_rate: float = 0.02,
    ) -> None:
        """
        Args:
            sensor_id: Unique identifier for the sensor.
            initial_trust: Starting trust level [0, 1].
            decay_rate: How fast trust decays per degradation trigger.
            recovery_rate: How fast trust recovers per good signal.
        """
        self.sensor_id = sensor_id
        self._trust: float = float(np.clip(initial_trust, 0.0, 1.0))
        self.decay_rate = decay_rate
        self.recovery_rate = recovery_rate
        self._degradation_reasons: list[str] = []
        self._last_updated: datetime = datetime.now(UTC)

    @property
    def trust_value(self) -> float:
        return self._trust

    def update(self, signal: SensorSignal) -> TrustState:
        """
        Update trust given a new sensor quality signal.

        Returns the new TrustState.
        """
        reasons: list[str] = []
        decay_factor = 1.0

        # Depth variance spike
        if signal.depth_variance > 0.5:
            penalty = signal.depth_variance * self.decay_rate * 2
            decay_factor -= penalty
            reasons.append(f"depth_variance={signal.depth_variance:.2f}")

        # Low lighting
        if signal.lighting_quality < 0.4:
            penalty = (1 - signal.lighting_quality) * self.decay_rate
            decay_factor -= penalty
            reasons.append(f"lighting_quality={signal.lighting_quality:.2f}")

        # Inconsistent detections
        if signal.detection_consistency < 0.5:
            penalty = (1 - signal.detection_consistency) * self.decay_rate
            decay_factor -= penalty
            reasons.append(f"detection_consistency={signal.detection_consistency:.2f}")

        # Noise spikes
        if signal.noise_level > 0.6:
            penalty = signal.noise_level * self.decay_rate
            decay_factor -= penalty
            reasons.append(f"noise_level={signal.noise_level:.2f}")

        # Frame rate drops
        if signal.frame_rate < signal.min_frame_rate:
            drop_ratio = 1.0 - signal.frame_rate / signal.min_frame_rate
            penalty = drop_ratio * self.decay_rate
            decay_factor -= penalty
            reasons.append(f"frame_rate={signal.frame_rate:.1f}fps")

        # Apply decay / recovery
        decay_factor = max(decay_factor, 0.5)  # Cap maximum single-step decay
        new_trust = self._trust * decay_factor

        # Recovery when everything is nominal
        if not reasons:
            new_trust = min(1.0, new_trust + self.recovery_rate)

        self._trust = float(np.clip(new_trust, 0.0, 1.0))
        self._degradation_reasons = reasons
        self._last_updated = datetime.now(UTC)

        return self.get_state()

    def get_state(self) -> TrustState:
        """Return current TrustState."""
        return TrustState(
            sensor_id=self.sensor_id,
            trust_value=self._trust,
            degradation_reasons=list(self._degradation_reasons),
            last_updated=self._last_updated,
        )

    def reset(self, trust: float = 1.0) -> None:
        """Reset trust to a given value (e.g. after sensor replacement)."""
        self._trust = float(np.clip(trust, 0.0, 1.0))
        self._degradation_reasons = []
        self._last_updated = datetime.now(UTC)
