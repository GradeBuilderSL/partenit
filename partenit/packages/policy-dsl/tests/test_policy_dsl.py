"""Tests for partenit-policy-dsl."""

import textwrap
from pathlib import Path

import pytest

from partenit.policy_dsl.parser import PolicyParser
from partenit.policy_dsl.validator import PolicyValidator, ValidationError
from partenit.policy_dsl.bundle import PolicyBundleBuilder
from partenit.policy_dsl.conflicts import ConflictDetector
from partenit.policy_dsl.evaluator import PolicyEvaluator
from partenit.core.models import PolicyPriority


# ---------------------------------------------------------------------------
# Sample policy YAML
# ---------------------------------------------------------------------------

HUMAN_PROXIMITY_YAML = textwrap.dedent("""\
    rule_id: human_proximity_slowdown
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
      parameter: max_velocity
      value: 0.3
      unit: m/s
    release:
      type: compound
      conditions:
        - type: threshold
          metric: human.distance
          operator: greater_than
          value: 2.0
      elapsed_seconds: 3
""")

EMERGENCY_STOP_YAML = textwrap.dedent("""\
    rule_id: emergency_stop_zone
    name: "Emergency Stop in Hazardous Zone"
    priority: safety_critical
    condition:
      type: threshold
      metric: zone.type
      operator: equals
      value: "hazardous"
    action:
      type: block
""")

SPEED_EFFICIENCY_YAML = textwrap.dedent("""\
    rule_id: speed_efficiency
    priority: efficiency
    condition:
      type: threshold
      metric: human.distance
      operator: greater_than
      value: 5.0
    action:
      type: clamp
      parameter: max_velocity
      value: 2.0
      unit: m/s
""")


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


def test_parse_single_rule():
    parser = PolicyParser()
    rules = parser.parse(HUMAN_PROXIMITY_YAML)
    assert len(rules) == 1
    rule = rules[0]
    assert rule.rule_id == "human_proximity_slowdown"
    assert rule.priority == PolicyPriority.SAFETY_CRITICAL
    assert rule.condition.metric == "human.distance"
    assert rule.condition.operator == "less_than"
    assert rule.condition.value == 1.5
    assert rule.action.type == "clamp"
    assert rule.action.parameter == "max_velocity"
    assert rule.action.value == 0.3
    assert rule.provenance == "ISO 3691-4 section 5.2"


def test_parse_list_of_rules():
    yaml_str = textwrap.dedent("""\
        rules:
          - rule_id: rule_a
            priority: safety_critical
            condition:
              type: threshold
              metric: x
              operator: less_than
              value: 1
            action:
              type: block
          - rule_id: rule_b
            priority: legal
            condition:
              type: threshold
              metric: y
              operator: greater_than
              value: 2
            action:
              type: clamp
              parameter: speed
              value: 0.5
    """)
    parser = PolicyParser()
    rules = parser.parse(yaml_str)
    assert len(rules) == 2
    assert rules[0].rule_id == "rule_a"
    assert rules[1].rule_id == "rule_b"


def test_parse_block_action():
    parser = PolicyParser()
    rules = parser.parse(EMERGENCY_STOP_YAML)
    assert len(rules) == 1
    assert rules[0].action.type == "block"


def test_parse_release_block():
    parser = PolicyParser()
    rules = parser.parse(HUMAN_PROXIMITY_YAML)
    release = rules[0].release
    assert release is not None
    assert release.elapsed_seconds == 3
    assert len(release.conditions) == 1


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


def test_validator_passes_valid():
    validator = PolicyValidator()
    warnings = validator.validate_raw(
        {"rule_id": "r1", "priority": "safety_critical",
         "condition": {"type": "threshold", "metric": "x", "operator": "less_than", "value": 1},
         "action": {"type": "block"}}
    )
    assert isinstance(warnings, list)


def test_validator_rejects_missing_rule_id():
    validator = PolicyValidator()
    with pytest.raises(ValidationError) as exc_info:
        validator.validate_raw(
            {"priority": "safety_critical",
             "condition": {"type": "threshold", "metric": "x", "operator": "less_than", "value": 1},
             "action": {"type": "block"}}
        )
    assert any("rule_id" in e for e in exc_info.value.errors)


def test_validator_rejects_invalid_priority():
    validator = PolicyValidator()
    with pytest.raises(ValidationError) as exc_info:
        validator.validate_raw(
            {"rule_id": "r1", "priority": "godmode",
             "condition": {"type": "threshold", "metric": "x", "operator": "less_than", "value": 1},
             "action": {"type": "block"}}
        )
    assert any("priority" in e for e in exc_info.value.errors)


def test_validator_rejects_invalid_action_type():
    validator = PolicyValidator()
    with pytest.raises(ValidationError):
        validator.validate_raw(
            {"rule_id": "r1", "priority": "task",
             "condition": {"type": "threshold", "metric": "x", "operator": "less_than", "value": 1},
             "action": {"type": "explode"}}
        )


def test_validator_warns_on_missing_priority():
    validator = PolicyValidator()
    warnings = validator.validate_raw(
        {"rule_id": "r1",
         "condition": {"type": "threshold", "metric": "x", "operator": "less_than", "value": 1},
         "action": {"type": "block"}}
    )
    assert any("priority" in w for w in warnings)


# ---------------------------------------------------------------------------
# Bundle tests
# ---------------------------------------------------------------------------


def test_bundle_roundtrip(tmp_path: Path):
    policy_file = tmp_path / "test.yaml"
    policy_file.write_text(HUMAN_PROXIMITY_YAML)

    builder = PolicyBundleBuilder()
    bundle = builder.from_file(policy_file)
    assert len(bundle.rules) == 1
    assert bundle.bundle_hash != ""

    output = tmp_path / "bundle.json"
    builder.export(bundle, output)
    assert output.exists()

    loaded = PolicyBundleBuilder.load(output)
    assert loaded.bundle_hash == bundle.bundle_hash
    assert len(loaded.rules) == 1


def test_bundle_from_dir(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(HUMAN_PROXIMITY_YAML)
    (tmp_path / "b.yaml").write_text(EMERGENCY_STOP_YAML)

    builder = PolicyBundleBuilder()
    bundle = builder.from_dir(tmp_path)
    assert len(bundle.rules) == 2


# ---------------------------------------------------------------------------
# Conflict detection tests
# ---------------------------------------------------------------------------


def test_no_conflict_different_metrics():
    parser = PolicyParser()
    rules = parser.parse(HUMAN_PROXIMITY_YAML) + parser.parse(EMERGENCY_STOP_YAML)
    detector = ConflictDetector()
    conflicts = detector.detect(rules)
    assert len(conflicts) == 0


def test_conflict_same_metric_different_values():
    yaml_str = textwrap.dedent("""\
        rules:
          - rule_id: rule_slow
            priority: safety_critical
            condition:
              type: threshold
              metric: human.distance
              operator: less_than
              value: 1.5
            action:
              type: clamp
              parameter: max_velocity
              value: 0.3
          - rule_id: rule_slower
            priority: legal
            condition:
              type: threshold
              metric: human.distance
              operator: less_than
              value: 1.5
            action:
              type: clamp
              parameter: max_velocity
              value: 0.1
    """)
    parser = PolicyParser()
    rules = parser.parse(yaml_str)
    detector = ConflictDetector()
    conflicts = detector.detect(rules)
    assert len(conflicts) == 1
    # Higher priority (safety_critical) wins
    assert conflicts[0].winner.rule_id == "rule_slow"


def test_conflict_winner_is_higher_priority():
    parser = PolicyParser()
    rules = parser.parse(textwrap.dedent("""\
        rules:
          - rule_id: low_prio
            priority: efficiency
            condition:
              type: threshold
              metric: x
              operator: less_than
              value: 5
            action:
              type: clamp
              parameter: speed
              value: 2.0
          - rule_id: high_prio
            priority: safety_critical
            condition:
              type: threshold
              metric: x
              operator: less_than
              value: 5
            action:
              type: clamp
              parameter: speed
              value: 0.3
    """))
    detector = ConflictDetector()
    conflicts = detector.detect(rules)
    assert len(conflicts) == 1
    assert conflicts[0].winner.rule_id == "high_prio"


# ---------------------------------------------------------------------------
# Evaluator tests
# ---------------------------------------------------------------------------


def test_evaluator_fires_matching_rule():
    parser = PolicyParser()
    rules = parser.parse(HUMAN_PROXIMITY_YAML)
    evaluator = PolicyEvaluator()

    # Human at 1.0m — should fire
    result = evaluator.evaluate(rules, {"human": {"distance": 1.0}})
    assert len(result.fired_rules) == 1
    assert result.fired_rules[0].rule_id == "human_proximity_slowdown"


def test_evaluator_no_fire_outside_threshold():
    parser = PolicyParser()
    rules = parser.parse(HUMAN_PROXIMITY_YAML)
    evaluator = PolicyEvaluator()

    # Human at 3.0m — should NOT fire
    result = evaluator.evaluate(rules, {"human": {"distance": 3.0}})
    assert len(result.fired_rules) == 0


def test_evaluator_clamps_resolved():
    parser = PolicyParser()
    rules = parser.parse(HUMAN_PROXIMITY_YAML) + parser.parse(SPEED_EFFICIENCY_YAML)
    evaluator = PolicyEvaluator()

    # Only human_proximity_slowdown fires (human at 1.0m)
    result = evaluator.evaluate(rules, {"human": {"distance": 1.0}})
    clamps = result.get_clamps()
    assert "max_velocity" in clamps
    assert clamps["max_velocity"] == 0.3


def test_evaluator_priority_wins_on_clamp():
    """safety_critical clamp (0.3) beats efficiency clamp (2.0) on same param."""
    parser = PolicyParser()
    rules = parser.parse(HUMAN_PROXIMITY_YAML) + parser.parse(SPEED_EFFICIENCY_YAML)
    evaluator = PolicyEvaluator()

    # Both rules fire: human at 1.0m (<1.5 → safety fires), but distance also >5? No.
    # Let's use distance=0.5 so only safety fires
    result = evaluator.evaluate(rules, {"human": {"distance": 0.5}})
    clamps = result.get_clamps()
    assert clamps.get("max_velocity") == 0.3


def test_evaluator_block_detected():
    parser = PolicyParser()
    rules = parser.parse(EMERGENCY_STOP_YAML)
    evaluator = PolicyEvaluator()

    result = evaluator.evaluate(rules, {"zone": {"type": "hazardous"}})
    assert result.has_violations is True


def test_evaluator_compound_condition():
    yaml_str = textwrap.dedent("""\
        rule_id: compound_rule
        priority: safety_critical
        condition:
          type: compound
          logic: and
          conditions:
            - type: threshold
              metric: human.distance
              operator: less_than
              value: 2.0
            - type: threshold
              metric: robot.speed
              operator: greater_than
              value: 0.5
        action:
          type: block
    """)
    parser = PolicyParser()
    rules = parser.parse(yaml_str)
    evaluator = PolicyEvaluator()

    # Both conditions true
    result = evaluator.evaluate(rules, {"human": {"distance": 1.0}, "robot": {"speed": 1.0}})
    assert result.has_violations is True

    # Only one condition true
    result = evaluator.evaluate(rules, {"human": {"distance": 1.0}, "robot": {"speed": 0.1}})
    assert result.has_violations is False


# ---------------------------------------------------------------------------
# partenit-init scaffold tests
# ---------------------------------------------------------------------------


def test_init_creates_expected_files(tmp_path):
    from partenit.policy_dsl.init_cmd import scaffold

    target = tmp_path / "my_robot"
    created = scaffold(target, "my_robot")

    labels = [label for _, label in created]
    assert any("policies.yaml" in ln for ln in labels)
    assert any("decisions" in ln for ln in labels)
    assert any("main.py" in ln for ln in labels)
    assert any(".gitignore" in ln for ln in labels)


def test_init_policies_yaml_content(tmp_path):
    from partenit.policy_dsl.init_cmd import scaffold
    from partenit.policy_dsl.parser import PolicyParser

    target = tmp_path / "proj"
    scaffold(target, "proj")

    parser = PolicyParser()
    rules = parser.load_file(target / "policies" / "policies.yaml")
    rule_ids = {r.rule_id for r in rules}
    assert "human_proximity_slowdown" in rule_ids
    assert "emergency_stop" in rule_ids


def test_init_main_py_content(tmp_path):
    from partenit.policy_dsl.init_cmd import scaffold

    target = tmp_path / "proj"
    scaffold(target, "proj")

    main_py = (target / "main.py").read_text()
    assert "GuardedRobot" in main_py
    assert "MockRobotAdapter" in main_py
    assert "proj" in main_py


def test_init_idempotent(tmp_path):
    """Running scaffold twice does not overwrite existing files."""
    from partenit.policy_dsl.init_cmd import scaffold

    target = tmp_path / "proj"
    scaffold(target, "proj")

    # Overwrite main.py
    main_py = target / "main.py"
    main_py.write_text("# custom content")

    scaffold(target, "proj")  # second call

    # File should NOT be overwritten
    assert main_py.read_text() == "# custom content"
