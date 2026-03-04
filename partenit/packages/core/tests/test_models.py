"""Tests for partenit-core data contracts."""

import hashlib
import json
from datetime import datetime

import pytest

from partenit.core.models import (
    DecisionFingerprint,
    DecisionPacket,
    GuardDecision,
    PolicyAction,
    PolicyBundle,
    PolicyCondition,
    PolicyPriority,
    PolicyRule,
    RiskScore,
    SafetyEvent,
    SafetyEventType,
    StructuredObservation,
    TrustMode,
    TrustState,
)


# ---------------------------------------------------------------------------
# StructuredObservation
# ---------------------------------------------------------------------------


def test_observation_treat_as_human_auto():
    obs = StructuredObservation(
        object_id="obj-1",
        class_best="person",
        class_set=["person", "human"],
        position_3d=(1.0, 0.0, 0.0),
        confidence=0.9,
    )
    assert obs.treat_as_human is True


def test_observation_no_human_in_set():
    obs = StructuredObservation(
        object_id="obj-2",
        class_best="forklift",
        class_set=["forklift", "vehicle"],
        position_3d=(3.0, 0.0, 0.0),
        confidence=0.85,
    )
    assert obs.treat_as_human is False


def test_observation_distance():
    obs = StructuredObservation(
        object_id="obj-3",
        class_best="box",
        position_3d=(3.0, 4.0, 0.0),
        confidence=0.7,
    )
    assert abs(obs.distance() - 5.0) < 1e-6


# ---------------------------------------------------------------------------
# PolicyPriority ordering
# ---------------------------------------------------------------------------


def test_priority_ordering():
    assert PolicyPriority.SAFETY_CRITICAL.numeric > PolicyPriority.LEGAL.numeric
    assert PolicyPriority.LEGAL.numeric > PolicyPriority.TASK.numeric
    assert PolicyPriority.TASK.numeric > PolicyPriority.EFFICIENCY.numeric


# ---------------------------------------------------------------------------
# PolicyBundle hash
# ---------------------------------------------------------------------------


def _make_rule(rule_id: str) -> PolicyRule:
    return PolicyRule(
        rule_id=rule_id,
        name=f"Rule {rule_id}",
        priority=PolicyPriority.SAFETY_CRITICAL,
        condition=PolicyCondition(
            type="threshold",
            metric="human.distance",
            operator="less_than",
            value=1.5,
            unit="meters",
        ),
        action=PolicyAction(type="block"),
        provenance="test",
    )


def test_bundle_hash_computed():
    bundle = PolicyBundle(rules=[_make_rule("r1"), _make_rule("r2")])
    assert bundle.bundle_hash != ""
    assert len(bundle.bundle_hash) == 64  # sha256 hex


def test_bundle_hash_deterministic():
    b1 = PolicyBundle(rules=[_make_rule("r1")])
    b2 = PolicyBundle(rules=[_make_rule("r1")])
    assert b1.bundle_hash == b2.bundle_hash


def test_bundle_hash_changes_with_rules():
    b1 = PolicyBundle(rules=[_make_rule("r1")])
    b2 = PolicyBundle(rules=[_make_rule("r2")])
    assert b1.bundle_hash != b2.bundle_hash


# ---------------------------------------------------------------------------
# TrustState mode
# ---------------------------------------------------------------------------


def test_trust_mode_nominal():
    ts = TrustState(sensor_id="cam-0", trust_value=0.95)
    assert ts.mode == TrustMode.NOMINAL


def test_trust_mode_degraded():
    ts = TrustState(sensor_id="cam-0", trust_value=0.7)
    assert ts.mode == TrustMode.DEGRADED


def test_trust_mode_unreliable():
    ts = TrustState(sensor_id="cam-0", trust_value=0.35)
    assert ts.mode == TrustMode.UNRELIABLE


def test_trust_mode_failed():
    ts = TrustState(sensor_id="cam-0", trust_value=0.1)
    assert ts.mode == TrustMode.FAILED


# ---------------------------------------------------------------------------
# DecisionPacket fingerprint
# ---------------------------------------------------------------------------


def _make_packet(action: str = "navigate_to") -> DecisionPacket:
    risk = RiskScore(value=0.3, contributors={"distance": 0.2, "velocity": 0.1})
    decision = GuardDecision(
        allowed=True,
        risk_score=risk,
        applied_policies=["human_proximity"],
    )
    return DecisionPacket(
        action_requested=action,
        action_params={"zone": "A3", "speed": 1.5},
        guard_decision=decision,
    )


def test_fingerprint_computed():
    packet = _make_packet()
    fp = packet.compute_fingerprint()
    assert len(fp) == 64
    assert isinstance(fp, str)


def test_fingerprint_deterministic():
    # Two packets with same content should have same fingerprint
    p1 = _make_packet()
    # Re-compute fingerprint
    assert p1.compute_fingerprint() == p1.compute_fingerprint()


def test_fingerprint_changes_on_tamper():
    packet = _make_packet()
    fp1 = packet.compute_fingerprint()
    # Tamper with the decision
    tampered = packet.model_copy(
        update={"guard_decision": packet.guard_decision.model_copy(update={"allowed": False})}
    )
    fp2 = tampered.compute_fingerprint()
    assert fp1 != fp2


def test_decision_fingerprint_verify():
    packet = _make_packet()
    fp_str = packet.compute_fingerprint()
    df = DecisionFingerprint(fingerprint=fp_str, packet_id=packet.packet_id)
    assert df.verify(packet) is True


def test_decision_fingerprint_rejects_tampered():
    packet = _make_packet()
    df = DecisionFingerprint(
        fingerprint=packet.compute_fingerprint(), packet_id=packet.packet_id
    )
    tampered = packet.model_copy(
        update={"mission_goal": "HACKED"}
    )
    assert df.verify(tampered) is False


# ---------------------------------------------------------------------------
# GuardDecision
# ---------------------------------------------------------------------------


def test_guard_decision_blocked():
    risk = RiskScore(value=0.9)
    decision = GuardDecision(
        allowed=False,
        rejection_reason="Speed exceeds limit in human zone",
        risk_score=risk,
        applied_policies=["human_proximity_slowdown"],
    )
    assert decision.allowed is False
    assert decision.rejection_reason is not None


def test_guard_decision_modified_params():
    risk = RiskScore(value=0.4)
    decision = GuardDecision(
        allowed=True,
        modified_params={"speed": 0.3},
        risk_score=risk,
        applied_policies=["human_proximity_slowdown"],
    )
    assert decision.modified_params["speed"] == 0.3
