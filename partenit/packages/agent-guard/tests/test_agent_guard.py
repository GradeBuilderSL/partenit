"""Tests for partenit-agent-guard."""

import textwrap
from pathlib import Path

import pytest

from partenit.agent_guard.core import AgentGuard
from partenit.agent_guard.risk import compute_risk
from partenit.core.models import StructuredObservation


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WAREHOUSE_POLICY_YAML = textwrap.dedent("""\
    rules:
      - rule_id: human_proximity_slowdown
        name: "Human Proximity Speed Limit"
        priority: safety_critical
        provenance: "ISO 3691-4 section 5.2"
        condition:
          type: threshold
          metric: human.distance
          operator: less_than
          value: 1.5
          unit: meters
        action:
          type: clamp
          parameter: speed
          value: 0.3
          unit: m/s

      - rule_id: hazardous_zone_block
        name: "Hazardous Zone Block"
        priority: safety_critical
        condition:
          type: threshold
          metric: zone.type
          operator: equals
          value: "hazardous"
        action:
          type: block

      - rule_id: speed_efficiency
        name: "Nominal speed cap"
        priority: efficiency
        condition:
          type: threshold
          metric: human.distance
          operator: greater_than
          value: 5.0
        action:
          type: clamp
          parameter: speed
          value: 2.0
""")


@pytest.fixture
def policy_file(tmp_path: Path) -> Path:
    f = tmp_path / "warehouse.yaml"
    f.write_text(WAREHOUSE_POLICY_YAML)
    return f


@pytest.fixture
def guard(policy_file: Path) -> AgentGuard:
    g = AgentGuard(risk_threshold=0.85)
    g.load_policies(policy_file)
    return g


# ---------------------------------------------------------------------------
# Basic allow/block
# ---------------------------------------------------------------------------


def test_allowed_when_no_humans_nearby(guard: AgentGuard):
    decision = guard.check_action(
        action="navigate_to",
        params={"zone": "A3", "speed": 1.5},
        context={"human": {"distance": 10.0}},
    )
    assert decision.allowed is True


def test_blocked_in_hazardous_zone(guard: AgentGuard):
    decision = guard.check_action(
        action="navigate_to",
        params={"zone": "HAZ-1", "speed": 1.0},
        context={"zone": {"type": "hazardous"}},
    )
    assert decision.allowed is False
    assert "hazardous_zone_block" in decision.rejection_reason


def test_speed_clamped_near_human(guard: AgentGuard):
    decision = guard.check_action(
        action="navigate_to",
        params={"zone": "A3", "speed": 2.0},
        context={"human": {"distance": 1.0}},
    )
    # Rule fires and clamps speed
    assert "human_proximity_slowdown" in decision.applied_policies
    assert decision.modified_params is not None
    assert decision.modified_params["speed"] <= 0.3


def test_original_speed_preserved_if_already_within_clamp(guard: AgentGuard):
    """If requested speed is already within clamp value, no modification needed."""
    decision = guard.check_action(
        action="navigate_to",
        params={"zone": "A3", "speed": 0.2},
        context={"human": {"distance": 1.0}},
    )
    # Guard fires but speed is already ≤ 0.3, so params unchanged
    if decision.modified_params:
        assert decision.modified_params["speed"] <= 0.3


def test_no_policies_loaded_allows_low_risk():
    guard = AgentGuard(risk_threshold=0.9)
    decision = guard.check_action(
        action="navigate_to",
        params={"speed": 0.5},
        context={},
    )
    assert decision.allowed is True


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------


def test_risk_score_present():
    guard = AgentGuard()
    decision = guard.check_action(
        action="navigate_to",
        params={"speed": 1.5},
        context={"human": {"distance": 2.0}},
    )
    assert 0.0 <= decision.risk_score.value <= 1.0


def test_risk_increases_near_human():
    r_far = compute_risk("navigate_to", {"speed": 1.0}, {"human": {"distance": 10.0}})
    r_near = compute_risk("navigate_to", {"speed": 1.0}, {"human": {"distance": 0.5}})
    assert r_near.value > r_far.value


def test_risk_increases_with_speed():
    r_slow = compute_risk("navigate_to", {"speed": 0.3}, {})
    r_fast = compute_risk("navigate_to", {"speed": 3.0}, {})
    assert r_fast.value > r_slow.value


def test_risk_contributors_present():
    risk = compute_risk("navigate_to", {"speed": 1.0}, {"human": {"distance": 2.0}})
    assert "distance" in risk.contributors
    assert "speed" in risk.contributors
    assert "trust" in risk.contributors


def test_risk_with_observations():
    obs = StructuredObservation(
        object_id="h1",
        class_best="human",
        class_set=["human"],
        position_3d=(1.0, 0.0, 0.0),
        confidence=0.9,
        sensor_trust=0.5,
    )
    risk = compute_risk("navigate_to", {"speed": 1.0}, {}, observations=[obs])
    assert risk.contributors["trust"] > 0.0  # Low trust -> higher risk


# ---------------------------------------------------------------------------
# Policy application tracking
# ---------------------------------------------------------------------------


def test_applied_policies_recorded(guard: AgentGuard):
    decision = guard.check_action(
        action="navigate_to",
        params={"speed": 2.0},
        context={"human": {"distance": 1.0}},
    )
    assert "human_proximity_slowdown" in decision.applied_policies


def test_no_policies_fired_for_safe_context(guard: AgentGuard):
    decision = guard.check_action(
        action="navigate_to",
        params={"speed": 1.0},
        context={"human": {"distance": 8.0}},
    )
    # Neither proximity nor hazardous zone rule fires
    assert "human_proximity_slowdown" not in decision.applied_policies
    assert "hazardous_zone_block" not in decision.applied_policies


# ---------------------------------------------------------------------------
# Safety events
# ---------------------------------------------------------------------------


def test_events_emitted_on_block(guard: AgentGuard):
    guard.clear_events()
    guard.check_action(
        action="navigate_to",
        params={"speed": 1.0},
        context={"zone": {"type": "hazardous"}},
    )
    events = guard.get_events()
    assert len(events) >= 1
    from partenit.core.models import SafetyEventType
    assert any(e.event_type == SafetyEventType.LLM_BLOCKED for e in events)


# ---------------------------------------------------------------------------
# Bundle loading
# ---------------------------------------------------------------------------


def test_load_bundle_directly(tmp_path: Path):
    from partenit.policy_dsl.bundle import PolicyBundleBuilder

    policy_file = tmp_path / "p.yaml"
    policy_file.write_text(WAREHOUSE_POLICY_YAML)
    bundle = PolicyBundleBuilder().from_file(policy_file)

    guard = AgentGuard()
    guard.load_bundle(bundle)

    decision = guard.check_action(
        action="navigate_to",
        params={"speed": 2.0},
        context={"human": {"distance": 1.0}},
    )
    assert "human_proximity_slowdown" in decision.applied_policies


def test_load_bundle_json(tmp_path: Path):
    from partenit.policy_dsl.bundle import PolicyBundleBuilder

    policy_file = tmp_path / "p.yaml"
    policy_file.write_text(WAREHOUSE_POLICY_YAML)
    builder = PolicyBundleBuilder()
    bundle = builder.from_file(policy_file)
    bundle_path = tmp_path / "bundle.json"
    builder.export(bundle, bundle_path)

    guard = AgentGuard()
    guard.load_policies(bundle_path)

    decision = guard.check_action(
        action="navigate_to",
        params={"speed": 2.0},
        context={"human": {"distance": 1.0}},
    )
    assert decision.allowed is True  # Speed clamped, not blocked


# ---------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------


def test_decision_has_latency(guard: AgentGuard):
    decision = guard.check_action(
        action="navigate_to",
        params={"speed": 1.0},
        context={"human": {"distance": 5.0}},
    )
    assert decision.latency_ms >= 0.0


# ---------------------------------------------------------------------------
# ROS2SkillGuard
# ---------------------------------------------------------------------------


def test_ros2_skill_guard_allow(tmp_path: Path) -> None:
    """Goal within safe distance — guard allows, no modified params."""
    policy_yaml = textwrap.dedent("""\
        rule_id: human_proximity_slowdown
        name: "Human Proximity Speed Limit"
        priority: safety_critical
        condition:
          type: threshold
          metric: human.distance
          operator: less_than
          value: 1.5
        action:
          type: clamp
          parameter: speed
          value: 0.3
    """)
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(policy_yaml)

    from partenit.agent_guard import ROS2SkillGuard

    guard = AgentGuard()
    guard.load_policies(policy_file)
    ros2_guard = ROS2SkillGuard(guard)

    decision = ros2_guard.check_goal(
        action_name="navigate_to_pose",
        goal={"pose": {"x": 5.0, "y": 0.0}, "speed": 1.0},
        context={"human": {"distance": 5.0}},
    )
    assert decision.allowed is True


def test_ros2_skill_guard_clamps_speed(tmp_path: Path) -> None:
    """Human nearby — guard clamps speed in modified_params."""
    policy_yaml = textwrap.dedent("""\
        rule_id: speed_clamp
        name: Speed Clamp
        priority: safety_critical
        condition:
          type: threshold
          metric: human.distance
          operator: less_than
          value: 2.0
        action:
          type: clamp
          parameter: speed
          value: 0.3
    """)
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(policy_yaml)

    from partenit.agent_guard import ROS2SkillGuard

    guard = AgentGuard()
    guard.load_policies(policy_file)
    ros2_guard = ROS2SkillGuard(guard)

    decision = ros2_guard.check_goal(
        action_name="navigate_to_pose",
        goal={"pose": {"x": 3.0, "y": 0.0}, "speed": 2.0},
        context={"human": {"distance": 1.2}},
    )
    assert decision.allowed is True
    assert decision.modified_params is not None
    assert decision.modified_params.get("speed") == pytest.approx(0.3)


def test_ros2_skill_guard_blocks(tmp_path: Path) -> None:
    """Human too close — guard blocks the goal entirely."""
    policy_yaml = textwrap.dedent("""\
        rule_id: emergency_stop
        name: Emergency Stop
        priority: safety_critical
        condition:
          type: threshold
          metric: human.distance
          operator: less_than
          value: 1.0
        action:
          type: block
    """)
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(policy_yaml)

    from partenit.agent_guard import ROS2SkillGuard

    guard = AgentGuard()
    guard.load_policies(policy_file)
    ros2_guard = ROS2SkillGuard(guard)

    decision = ros2_guard.check_goal(
        action_name="navigate_to_pose",
        goal={"pose": {"x": 1.0, "y": 0.0}, "speed": 1.5},
        context={"human": {"distance": 0.4}},
    )
    assert decision.allowed is False
    assert decision.rejection_reason is not None


def test_ros2_skill_guard_service_call(tmp_path: Path) -> None:
    """check_service has same semantics as check_goal."""
    from partenit.agent_guard import ROS2SkillGuard

    guard = AgentGuard()  # No policies — allow all
    ros2_guard = ROS2SkillGuard(guard)

    decision = ros2_guard.check_service(
        service_name="set_velocity",
        request={"linear": 1.0, "angular": 0.0},
        context={},
    )
    assert decision.allowed is True


def test_ros2_skill_guard_no_context(tmp_path: Path) -> None:
    """check_goal works with context=None (no KeyError)."""
    from partenit.agent_guard import ROS2SkillGuard

    guard = AgentGuard()
    ros2_guard = ROS2SkillGuard(guard)

    decision = ros2_guard.check_goal(
        action_name="dock",
        goal={"dock_id": "station_1"},
        context=None,
    )
    assert isinstance(decision.allowed, bool)
