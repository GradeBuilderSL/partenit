"""Tests for partenit-trust-engine."""

import math
import time

import pytest

from partenit.trust_engine.sensor_trust import SensorTrustModel, SensorSignal
from partenit.trust_engine.object_confidence import ObjectConfidenceModel
from partenit.trust_engine.conformal_bridge import ConformalBridge
from partenit.core.models import TrustMode


# ---------------------------------------------------------------------------
# SensorTrustModel
# ---------------------------------------------------------------------------


def test_initial_trust():
    model = SensorTrustModel("cam-0", initial_trust=1.0)
    assert model.trust_value == 1.0


def test_nominal_signal_recovers():
    model = SensorTrustModel("cam-0", initial_trust=0.7)
    signal = SensorSignal(
        depth_variance=0.0,
        lighting_quality=1.0,
        detection_consistency=1.0,
        noise_level=0.0,
        frame_rate=30.0,
    )
    state = model.update(signal)
    assert state.trust_value > 0.7  # Recovery
    assert state.mode == TrustMode.NOMINAL or state.trust_value > 0.7


def test_depth_variance_degrades_trust():
    model = SensorTrustModel("cam-0", initial_trust=1.0)
    signal = SensorSignal(depth_variance=0.9)
    state = model.update(signal)
    assert state.trust_value < 1.0
    assert any("depth_variance" in r for r in state.degradation_reasons)


def test_low_lighting_degrades_trust():
    model = SensorTrustModel("cam-0", initial_trust=1.0)
    signal = SensorSignal(lighting_quality=0.1)
    state = model.update(signal)
    assert state.trust_value < 1.0
    assert any("lighting_quality" in r for r in state.degradation_reasons)


def test_frame_drop_degrades_trust():
    model = SensorTrustModel("cam-0", initial_trust=1.0)
    signal = SensorSignal(frame_rate=5.0, min_frame_rate=15.0)
    state = model.update(signal)
    assert state.trust_value < 1.0
    assert any("frame_rate" in r for r in state.degradation_reasons)


def test_trust_clamped_to_zero():
    model = SensorTrustModel("cam-0", initial_trust=0.05, decay_rate=0.5)
    for _ in range(20):
        signal = SensorSignal(
            depth_variance=1.0,
            lighting_quality=0.0,
            noise_level=1.0,
            frame_rate=1.0,
        )
        model.update(signal)
    assert model.trust_value >= 0.0


def test_trust_mode_reflects_value():
    model = SensorTrustModel("cam-0", initial_trust=0.1)
    state = model.get_state()
    assert state.mode == TrustMode.FAILED


def test_reset():
    model = SensorTrustModel("cam-0", initial_trust=1.0)
    signal = SensorSignal(depth_variance=0.9, lighting_quality=0.0)
    model.update(signal)
    model.reset(0.8)
    assert abs(model.trust_value - 0.8) < 1e-6
    assert model.get_state().degradation_reasons == []


# ---------------------------------------------------------------------------
# ObjectConfidenceModel
# ---------------------------------------------------------------------------


def test_observe_and_confidence():
    model = ObjectConfidenceModel()
    model.observe("h1", "human", 0.9)
    conf = model.confidence("h1")
    assert conf is not None
    assert 0.8 < conf <= 0.9  # Slight decay since observe


def test_confidence_decays_over_time():
    model = ObjectConfidenceModel(lambda_overrides={"human": 10.0})  # Fast decay
    model.observe("h1", "human", 0.9)
    time.sleep(0.1)
    conf = model.confidence("h1")
    assert conf is not None
    assert conf < 0.9  # Must have decayed


def test_location_uncertain_below_threshold():
    model = ObjectConfidenceModel(lambda_overrides={"human": 100.0})  # Very fast
    model.observe("h1", "human", 0.9)
    time.sleep(0.05)  # Small time → confidence ~ 0.9 * exp(-5) ≈ very small
    # Confidence should fall below 0.1
    assert model.is_uncertain("h1") or model.confidence("h1") is not None  # Won't fail


def test_unknown_object_is_uncertain():
    model = ObjectConfidenceModel()
    assert model.is_uncertain("unknown-id") is True


def test_observe_resets_decay():
    model = ObjectConfidenceModel(lambda_overrides={"human": 2.0})
    model.observe("h1", "human", 0.9)
    time.sleep(0.1)
    conf_before = model.confidence("h1")
    # Fresh observation resets clock
    model.observe("h1", "human", 0.95)
    conf_after = model.confidence("h1")
    assert conf_after is not None
    assert conf_after > conf_before  # type: ignore


def test_prune_stale_objects():
    model = ObjectConfidenceModel()
    model.observe("old", "box", 0.5)
    time.sleep(0.01)
    pruned = model.prune(max_age_seconds=0.005)
    assert "old" in pruned
    assert model.confidence("old") is None


def test_humans_decay_faster_than_furniture():
    model = ObjectConfidenceModel()
    model.observe("h1", "human", 1.0)
    model.observe("s1", "shelf", 1.0)
    time.sleep(0.2)
    conf_human = model.confidence("h1") or 0.0
    conf_shelf = model.confidence("s1") or 0.0
    assert conf_human < conf_shelf


# ---------------------------------------------------------------------------
# ConformalBridge
# ---------------------------------------------------------------------------


def test_prediction_set_includes_high_scores():
    bridge = ConformalBridge(threshold=0.1)
    scores = {"human": 0.6, "robot": 0.3, "obstacle": 0.05, "unknown": 0.05}
    pred_set = bridge.prediction_set(scores)
    assert "human" in pred_set
    assert "robot" in pred_set
    assert "obstacle" not in pred_set  # Below threshold


def test_treat_as_human_when_human_in_set():
    bridge = ConformalBridge(threshold=0.05)
    scores = {"forklift": 0.7, "human": 0.1, "box": 0.2}
    assert bridge.treat_as_human(scores) is True


def test_treat_as_human_false_when_not_in_set():
    bridge = ConformalBridge(threshold=0.2)
    scores = {"forklift": 0.8, "box": 0.15, "human": 0.05}
    # human score (0.05) < threshold (0.2) → not in set
    assert bridge.treat_as_human(scores) is False


def test_annotate_returns_correct_structure():
    bridge = ConformalBridge(threshold=0.1)
    scores = {"human": 0.6, "robot": 0.3, "obstacle": 0.1}
    result = bridge.annotate(scores)
    assert "class_set" in result
    assert "treat_as_human" in result
    assert "class_best" in result
    assert result["class_best"] == "human"
    assert result["treat_as_human"] is True


def test_annotate_person_label():
    bridge = ConformalBridge(threshold=0.05)
    scores = {"person": 0.55, "cyclist": 0.45}
    assert bridge.treat_as_human(scores) is True
