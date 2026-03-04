"""Tests for partenit-safety-bench."""

import textwrap
from pathlib import Path

import pytest

from partenit.safety_bench.world import MockWorld, WorldObject
from partenit.safety_bench.robot import MockRobot
from partenit.safety_bench.scenario import ScenarioRunner, ScenarioResult
from partenit.core.models import GuardDecision, RiskScore


# ---------------------------------------------------------------------------
# MockWorld
# ---------------------------------------------------------------------------


def test_world_empty_context():
    world = MockWorld()
    ctx = world.get_context()
    assert "human" not in ctx


def test_world_human_distance():
    world = MockWorld()
    world.set_robot_position(0, 0)
    world.add_object(WorldObject("h1", "human", x=3.0, y=4.0))
    ctx = world.get_context()
    assert "human" in ctx
    assert abs(ctx["human"]["distance"] - 5.0) < 0.01


def test_world_human_appears_at():
    world = MockWorld()
    world.add_object(WorldObject("h1", "human", x=3.0, y=0.0, appears_at=5.0))
    ctx = world.get_context()
    assert "human" not in ctx  # Not yet visible at t=0

    world.step(6.0)
    ctx = world.get_context()
    assert "human" in ctx


def test_world_step_moves_objects():
    world = MockWorld()
    obj = WorldObject("m1", "obstacle", x=0.0, y=0.0, vx=1.0, vy=0.0)
    world.add_object(obj)
    world.step(2.0)
    assert abs(obj.x - 2.0) < 0.01


def test_world_get_observations():
    world = MockWorld()
    world.set_robot_position(0, 0)
    world.add_object(WorldObject("h1", "human", x=2.0, y=0.0))
    obs = world.get_observations()
    assert len(obs) == 1
    assert obs[0].treat_as_human is True
    assert abs(obs[0].position_3d[0] - 2.0) < 0.01


# ---------------------------------------------------------------------------
# MockRobot
# ---------------------------------------------------------------------------


def _allow_decision(speed: float | None = None) -> GuardDecision:
    params = {"speed": speed} if speed else None
    return GuardDecision(
        allowed=True,
        modified_params=params,
        risk_score=RiskScore(value=0.1),
        applied_policies=[],
    )


def _block_decision() -> GuardDecision:
    return GuardDecision(
        allowed=False,
        rejection_reason="Human too close",
        risk_score=RiskScore(value=0.9),
        applied_policies=["human_proximity"],
    )


def test_robot_moves_toward_goal():
    robot = MockRobot(start_x=0, start_y=0, goal_x=5, goal_y=0, initial_speed=1.0)
    robot.step(1.0)
    assert robot.x > 0.0
    assert robot.x < 5.0


def test_robot_stops_on_block():
    robot = MockRobot(start_x=0, start_y=0, goal_x=5, goal_y=0, initial_speed=1.0)
    robot.step(1.0, _block_decision())
    assert robot.stopped is True


def test_robot_slows_on_clamped_speed():
    robot = MockRobot(start_x=0, start_y=0, goal_x=5, goal_y=0, initial_speed=2.0)
    robot.step(1.0, _allow_decision(speed=0.3))
    assert robot.current_speed == 0.3
    assert any(e["type"] == "slowdown" for e in robot.events)


def test_robot_reaches_goal():
    robot = MockRobot(start_x=0, start_y=0, goal_x=1, goal_y=0, initial_speed=2.0)
    for _ in range(20):
        robot.step(0.1)
    assert robot.reached_goal is True


def test_robot_reset():
    robot = MockRobot(start_x=0, start_y=0, goal_x=5, goal_y=0, initial_speed=1.0)
    robot.step(2.0)
    robot.reset()
    assert robot.x == 0.0
    assert robot.current_speed == 1.0
    assert not robot.events


# ---------------------------------------------------------------------------
# ScenarioRunner
# ---------------------------------------------------------------------------

SCENARIO_YAML = textwrap.dedent("""\
    scenario_id: test_human_crossing
    robot:
      start_position: [0, 0, 0]
      goal_position: [10, 0, 0]
      initial_speed: 1.5
    world:
      humans:
        - id: human_01
          start_position: [5, 0.5, 0]
          velocity: [0, -1.0, 0]
          arrival_time: 0.0
          confidence: 0.95
    policies: []
    expected_events:
      - at_time: 1.0
        event: slowdown
    duration: 15.0
    dt: 0.1
""")

SCENARIO_NO_HUMAN_YAML = textwrap.dedent("""\
    scenario_id: test_clear_path
    robot:
      start_position: [0, 0, 0]
      goal_position: [5, 0, 0]
      initial_speed: 1.0
    world:
      humans: []
    policies: []
    expected_events: []
    duration: 10.0
    dt: 0.1
""")


def test_scenario_loads_from_string():
    runner = ScenarioRunner()
    config = runner.load_str(SCENARIO_YAML)
    assert config.scenario_id == "test_human_crossing"
    assert config.initial_speed == 1.5
    assert len(config.humans) == 1


def test_scenario_run_without_guard():
    runner = ScenarioRunner()
    config = runner.load_str(SCENARIO_NO_HUMAN_YAML)
    result = runner.run(config, with_guard=False)
    assert result.scenario_id == "test_clear_path"
    assert result.decisions_total == 0  # No guard = no decisions
    assert result.reached_goal is True


def test_scenario_run_with_guard_no_policies(tmp_path: Path):
    """With guard but no policies loaded — should still allow all actions."""
    runner = ScenarioRunner()
    config = runner.load_str(SCENARIO_NO_HUMAN_YAML)
    result = runner.run(config, with_guard=True)
    assert result.decisions_blocked == 0
    assert result.reached_goal is True


def test_scenario_with_guard_blocks_near_human(tmp_path: Path):
    """With a blocking policy, guard should stop the robot near humans."""
    policy_yaml = textwrap.dedent("""\
        rule_id: emergency_stop_human
        name: Emergency stop near human
        priority: safety_critical
        condition:
          type: threshold
          metric: human.distance
          operator: less_than
          value: 2.0
        action:
          type: block
    """)
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(policy_yaml)

    scenario_yaml = textwrap.dedent(f"""\
        scenario_id: test_block
        robot:
          start_position: [0, 0, 0]
          goal_position: [10, 0, 0]
          initial_speed: 1.0
        world:
          humans:
            - id: h1
              start_position: [3, 0.5, 0]
              velocity: [0, 0, 0]
              arrival_time: 0.0
        policies:
          - {policy_file}
        expected_events:
          - at_time: 2.5
            event: stop
        duration: 15.0
        dt: 0.1
    """)

    runner = ScenarioRunner()
    config = runner.load_str(scenario_yaml)
    result = runner.run(config, with_guard=True)

    assert result.decisions_blocked > 0
    assert result.with_guard is True


def test_scenario_result_summary():
    runner = ScenarioRunner()
    config = runner.load_str(SCENARIO_NO_HUMAN_YAML)
    result = runner.run(config, with_guard=False)
    summary = result.summary()
    assert "test_clear_path" in summary
    assert "NO guard" in summary


def test_scenario_wall_time_recorded():
    runner = ScenarioRunner()
    config = runner.load_str(SCENARIO_NO_HUMAN_YAML)
    result = runner.run(config, with_guard=False)
    assert result.wall_time_ms >= 0.0


def test_scenario_block_rate():
    result = ScenarioResult(
        scenario_id="test",
        with_guard=True,
        duration_simulated=10.0,
        decisions_total=10,
        decisions_blocked=4,
    )
    assert abs(result.block_rate - 0.4) < 1e-6
