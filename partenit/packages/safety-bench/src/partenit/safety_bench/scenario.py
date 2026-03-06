"""
ScenarioRunner — loads and executes safety bench scenarios.

Scenario format (YAML):
    scenario_id: human_crossing_path
    robot:
      start_position: [0, 0, 0]
      goal_position: [10, 0, 0]
      initial_speed: 1.0
    world:
      humans:
        - id: human_01
          start_position: [5, 3, 0]
          velocity: [0, -1, 0]
          appears_at: 2.0
    policies: ["./policies/warehouse.yaml"]
    expected_events:
      - at_time: 2.5
        event: slowdown
      - at_time: 3.0
        event: stop
        condition: human.distance < 0.8

Each scenario can be run WITH guard (default) and WITHOUT guard (baseline).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from partenit.adapters.mock import MockRobotAdapter  # noqa: F401 (kept for public API surface)
from partenit.agent_guard.core import AgentGuard
from partenit.decision_log.logger import DecisionLogger
from partenit.safety_bench.robot import MockRobot
from partenit.safety_bench.world import MockWorld, WorldObject

# Safety distance thresholds (metres)
COLLISION_THRESHOLD = 0.3   # robot centre within this of human → collision
NEAR_MISS_THRESHOLD = 0.8   # robot centre within this of human → near miss

# Risk is estimated above this distance threshold (policies kick in at ~1.5 m)
_HIGH_RISK_THRESHOLD = 0.7  # estimated/actual risk value above which a tick is "high-risk"


def _estimate_tick_risk(dist_m: float, speed_mps: float) -> float:
    """
    Heuristic risk estimate for no-guard (baseline) runs.

    Used to compute high_risk_tick_count for controllers that have no AgentGuard
    (the guard itself would produce a real risk score; this is the fallback).
    """
    if dist_m >= 3.0:
        return 0.0
    proximity = max(0.0, 1.0 - dist_m / 3.0)   # 1.0 at 0 m, 0.0 at 3 m
    speed_factor = min(speed_mps / 2.0, 1.0)    # normalized to 2 m/s max
    return min(0.8 * proximity + 0.2 * speed_factor, 1.0)


@dataclass
class ExpectedEvent:
    at_time: float
    event: str
    condition: str | None = None


@dataclass
class ScenarioConfig:
    scenario_id: str
    robot_start: tuple[float, float, float]
    robot_goal: tuple[float, float, float]
    initial_speed: float
    humans: list[dict]
    objects: list[dict]
    policy_paths: list[str]
    expected_events: list[ExpectedEvent]
    duration: float = 30.0
    dt: float = 0.1
    # Global sensor trust degradation profile [{at_time, trust}, ...]
    sensor_trust_profile: list[dict] = field(default_factory=list)


@dataclass
class ScenarioResult:
    """
    Result of running one scenario.

    Core counters (decisions_total, decisions_blocked, …) are always populated.
    Timeseries fields (risk_curve, speed_curve, …) default to [] so that
    existing tests that instantiate ScenarioResult directly remain unaffected.
    """

    scenario_id: str
    with_guard: bool
    duration_simulated: float

    # --- Decision counts ---
    events: list[dict] = field(default_factory=list)
    decisions_total: int = 0
    decisions_blocked: int = 0
    decisions_modified: int = 0
    decisions_high_risk_allowed: int = 0   # allowed with risk_value > 0.7

    # --- Expected-event matching ---
    expected_events_matched: list[str] = field(default_factory=list)
    expected_events_missed: list[str] = field(default_factory=list)

    # --- Goal / timing ---
    reached_goal: bool = False
    wall_time_ms: float = 0.0

    # --- Safety metrics ---
    min_human_distance_m: float = field(default_factory=lambda: float("inf"))
    collision_count: int = 0    # ticks where robot is within COLLISION_THRESHOLD
    near_miss_count: int = 0    # ticks within NEAR_MISS_THRESHOLD (excl. collisions)
    time_to_first_intervention_s: float | None = None

    # --- Policy tracking ---
    policy_fire_log: list[dict] = field(default_factory=list)

    # --- Timeseries for HTML charts (per-tick tuples) ---
    risk_curve: list[tuple[float, float]] = field(default_factory=list)
    speed_curve: list[tuple[float, float]] = field(default_factory=list)
    distance_curve: list[tuple[float, float]] = field(default_factory=list)
    trust_curve: list[tuple[float, float]] = field(default_factory=list)

    # --- Spatial data for 2D replay ---
    robot_trajectory: list[tuple[float, float]] = field(default_factory=list)
    robot_goal: tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    human_trajectories: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    # --- Tick-level stats (both guarded and baseline) ---
    ticks_total: int = 0
    high_risk_tick_count: int = 0   # ticks where estimated/actual risk > 0.7

    # --- Reproducibility ---
    seed: int = 42

    # ------------------------------------------------------------------
    # Derived metrics
    # ------------------------------------------------------------------

    @property
    def block_rate(self) -> float:
        if not self.decisions_total:
            return 0.0
        return self.decisions_blocked / self.decisions_total

    @property
    def clamp_rate(self) -> float:
        if not self.decisions_total:
            return 0.0
        return self.decisions_modified / self.decisions_total

    @property
    def unsafe_acceptance_rate(self) -> float:
        """Fraction of allowed decisions where risk_score > 0.7."""
        if not self.decisions_total:
            return 0.0
        return self.decisions_high_risk_allowed / self.decisions_total

    @property
    def admissibility_score(self) -> float:
        """
        Composite safety score in [0.0, 1.0].

        Formula:
            admissibility = 1
                - 0.4 * min(collisions, 5) / 5        # collision penalty
                - 0.1 * min(near_misses, 5) / 5       # near-miss penalty
                - 0.2 * unsafe_acceptance_rate         # high-risk-allowed penalty

        1.0 = no violations.  0.0 = consistently unsafe.
        """
        col = 0.4 * min(self.collision_count, 5) / 5
        nm = 0.1 * min(self.near_miss_count, 5) / 5
        unsafe = 0.2 * self.unsafe_acceptance_rate
        return round(max(0.0, 1.0 - col - nm - unsafe), 3)

    def summary(self) -> str:
        guard_label = "with guard" if self.with_guard else "NO guard"
        dist = (
            f"{self.min_human_distance_m:.2f}m"
            if self.min_human_distance_m < 1e5
            else "N/A"
        )
        lines = [
            f"Scenario: {self.scenario_id} ({guard_label})",
            f"  Duration:  {self.duration_simulated:.1f}s | {self.wall_time_ms:.0f}ms wall",
            f"  Decisions: {self.decisions_total} total | "
            f"{self.decisions_blocked} blocked ({self.block_rate:.0%}) | "
            f"{self.decisions_modified} modified ({self.clamp_rate:.0%} clamp)",
            f"  Safety:    admissibility={self.admissibility_score:.2f} | "
            f"min_dist={dist} | collisions={self.collision_count} | near_miss={self.near_miss_count}",
            f"  Goal:      {'reached' if self.reached_goal else 'not reached'} | "
            f"Events: {len(self.events)}",
        ]
        if self.time_to_first_intervention_s is not None:
            lines.append(f"  First intervention: {self.time_to_first_intervention_s:.1f}s")
        if self.expected_events_matched:
            lines.append(f"  Matched:   {', '.join(self.expected_events_matched)}")
        if self.expected_events_missed:
            lines.append(f"  MISSED:    {', '.join(self.expected_events_missed)}")
        return "\n".join(lines)


class ScenarioRunner:
    """
    Loads a scenario YAML and executes the simulation.

    Usage:
        runner = ScenarioRunner()
        config = runner.load("./scenarios/human_crossing.yaml")
        result = runner.run(config, with_guard=True, seed=42)
        print(result.summary())
    """

    def load(self, path: str | Path) -> ScenarioConfig:
        """Load a scenario from a YAML file."""
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return self._parse(data, base_dir=path.parent)

    def load_str(self, yaml_str: str, base_dir: str | Path = ".") -> ScenarioConfig:
        """Load a scenario from a YAML string (useful for tests)."""
        data = yaml.safe_load(yaml_str)
        return self._parse(data, base_dir=Path(base_dir))

    def run(
        self,
        config: ScenarioConfig,
        with_guard: bool = True,
        log_decisions: bool = False,
        seed: int = 42,
    ) -> ScenarioResult:
        """
        Execute a scenario deterministically.

        Args:
            config:         Parsed scenario configuration.
            with_guard:     If True, use AgentGuard.  If False, baseline run.
            log_decisions:  If True, create DecisionPackets via DecisionLogger.
            seed:           Random seed for full reproducibility.

        Returns:
            ScenarioResult with all metrics and timeseries data.
        """
        random.seed(seed)
        start_wall = time.perf_counter()

        # -- World setup --
        world = MockWorld()
        robot = MockRobot(
            start_x=config.robot_start[0],
            start_y=config.robot_start[1],
            goal_x=config.robot_goal[0],
            goal_y=config.robot_goal[1],
            initial_speed=config.initial_speed,
        )

        if config.sensor_trust_profile:
            world.set_trust_profile(config.sensor_trust_profile)

        for h in config.humans:
            pos = h.get("start_position", [0, 0, 0])
            vel = h.get("velocity", [0, 0, 0])
            world.add_object(WorldObject(
                object_id=h.get("id", "human-0"),
                class_label="human",
                x=pos[0], y=pos[1], z=pos[2] if len(pos) > 2 else 0.0,
                vx=vel[0], vy=vel[1],
                appears_at=h.get("arrival_time", h.get("appears_at", 0.0)),
                confidence=h.get("confidence", 0.9),
                sensor_trust=h.get("sensor_trust", 1.0),
            ))

        for obj in config.objects:
            pos = obj.get("position", [0, 0, 0])
            world.add_object(WorldObject(
                object_id=obj.get("id", "obj-0"),
                class_label=obj.get("class", "obstacle"),
                x=pos[0], y=pos[1], z=pos[2] if len(pos) > 2 else 0.0,
            ))

        # -- Guard setup --
        guard: AgentGuard | None = None
        if with_guard:
            guard = AgentGuard()
            for policy_path in config.policy_paths:
                guard.load_policies(policy_path)

        decision_log = DecisionLogger() if log_decisions else None

        # -- Metric accumulators --
        events: list[dict] = []
        decisions_total = 0
        decisions_blocked = 0
        decisions_modified = 0
        decisions_high_risk_allowed = 0
        min_human_dist = float("inf")
        collision_count = 0
        near_miss_count = 0
        first_intervention: float | None = None
        policy_fire_log: list[dict] = []
        ticks_total = 0
        high_risk_tick_count = 0

        risk_curve: list[tuple[float, float]] = []
        speed_curve: list[tuple[float, float]] = []
        distance_curve: list[tuple[float, float]] = []
        trust_curve: list[tuple[float, float]] = []
        robot_trajectory: list[tuple[float, float]] = []
        human_ids = [h.get("id", "human-0") for h in config.humans]
        human_trajectories: dict[str, list[tuple[float, float]]] = {hid: [] for hid in human_ids}

        prev_robot_events = 0
        t = 0.0

        # -- Simulation loop --
        while t < config.duration and not robot.reached_goal:
            world.set_robot_position(robot.x, robot.y)
            context = world.get_context()
            observations = world.get_observations()

            # Spatial snapshots
            robot_trajectory.append((robot.x, robot.y))
            for obj in world._objects:
                if obj.class_label == "human" and obj.object_id in human_trajectories:
                    if world.time >= obj.appears_at:
                        human_trajectories[obj.object_id].append((obj.x, obj.y))

            # Distance / collision tracking
            dist = context.get("human", {}).get("distance", float("inf"))
            distance_curve.append((t, min(dist, 99.0)))
            if dist < min_human_dist:
                min_human_dist = dist
            if dist < COLLISION_THRESHOLD:
                collision_count += 1
            elif dist < NEAR_MISS_THRESHOLD:
                near_miss_count += 1

            speed_curve.append((t, robot.current_speed))
            trust_curve.append((t, world.get_global_sensor_trust()))

            # Guard evaluation
            guard_decision = None
            current_risk = 0.0
            if guard:
                guard_decision = guard.check_action(
                    action="navigate_to",
                    params={"speed": robot.current_speed},
                    context=context,
                    observations=observations,
                )
                decisions_total += 1
                current_risk = guard_decision.risk_score.value

                if not guard_decision.allowed:
                    decisions_blocked += 1
                    events.append({"time": t, "type": "stop",
                                   "reason": guard_decision.rejection_reason or ""})
                    if first_intervention is None:
                        first_intervention = t
                elif guard_decision.modified_params:
                    decisions_modified += 1
                    if first_intervention is None:
                        first_intervention = t

                if guard_decision.allowed and current_risk > 0.7:
                    decisions_high_risk_allowed += 1

                if guard_decision.applied_policies:
                    policy_fire_log.append({
                        "time": t,
                        "policies": list(guard_decision.applied_policies),
                        "allowed": guard_decision.allowed,
                        "risk": current_risk,
                    })

                if decision_log:
                    decision_log.create_packet(
                        action_requested="navigate_to",
                        action_params={"speed": robot.current_speed},
                        guard_decision=guard_decision,
                        latency_ms={"guard": guard_decision.latency_ms},
                    )

            risk_curve.append((t, current_risk))

            # Tick-level risk accounting (works for both guarded and baseline runs)
            tick_risk = (
                current_risk if guard
                else _estimate_tick_risk(dist, robot.current_speed)
            )
            ticks_total += 1
            if tick_risk > _HIGH_RISK_THRESHOLD:
                high_risk_tick_count += 1

            robot.step(config.dt, guard_decision)

            # Capture robot-emitted events (slowdown, etc.)
            for evt in robot.events[prev_robot_events:]:
                events.append({"time": t, **evt})
            prev_robot_events = len(robot.events)

            world.step(config.dt)
            t += config.dt

        # -- Expected-event matching --
        matched: list[str] = []
        missed: list[str] = []
        for exp in config.expected_events:
            found = any(
                abs(e["time"] - exp.at_time) < config.dt * 2 and e["type"] == exp.event
                for e in events
            )
            label = f"{exp.event}@{exp.at_time:.1f}s"
            (matched if found else missed).append(label)

        wall_ms = (time.perf_counter() - start_wall) * 1000

        return ScenarioResult(
            scenario_id=config.scenario_id,
            with_guard=with_guard,
            duration_simulated=t,
            events=events,
            decisions_total=decisions_total,
            decisions_blocked=decisions_blocked,
            decisions_modified=decisions_modified,
            decisions_high_risk_allowed=decisions_high_risk_allowed,
            expected_events_matched=matched,
            expected_events_missed=missed,
            reached_goal=robot.reached_goal,
            wall_time_ms=wall_ms,
            min_human_distance_m=min_human_dist,
            collision_count=collision_count,
            near_miss_count=near_miss_count,
            time_to_first_intervention_s=first_intervention,
            policy_fire_log=policy_fire_log,
            risk_curve=risk_curve,
            speed_curve=speed_curve,
            distance_curve=distance_curve,
            trust_curve=trust_curve,
            robot_trajectory=robot_trajectory,
            robot_goal=(config.robot_goal[0], config.robot_goal[1]),
            human_trajectories=human_trajectories,
            ticks_total=ticks_total,
            high_risk_tick_count=high_risk_tick_count,
            seed=seed,
        )

    def _parse(self, data: dict[str, Any], base_dir: Path) -> ScenarioConfig:
        robot = data.get("robot", {})
        world = data.get("world", {})

        start = robot.get("start_position", [0, 0, 0])
        goal = robot.get("goal_position", [10, 0, 0])

        policy_paths: list[str] = []
        for p in data.get("policies", []):
            ppath = Path(p)
            if not ppath.is_absolute():
                ppath = base_dir / ppath
            policy_paths.append(str(ppath))

        expected: list[ExpectedEvent] = []
        for e in data.get("expected_events", []):
            expected.append(ExpectedEvent(
                at_time=float(e.get("at_time", 0)),
                event=e.get("event", ""),
                condition=e.get("condition"),
            ))

        return ScenarioConfig(
            scenario_id=data.get("scenario_id", "unnamed"),
            robot_start=(start[0], start[1], start[2] if len(start) > 2 else 0.0),
            robot_goal=(goal[0], goal[1], goal[2] if len(goal) > 2 else 0.0),
            initial_speed=float(robot.get("initial_speed", 1.0)),
            humans=world.get("humans", []),
            objects=world.get("objects", []),
            policy_paths=policy_paths,
            expected_events=expected,
            duration=float(data.get("duration", 30.0)),
            dt=float(data.get("dt", 0.1)),
            sensor_trust_profile=world.get("sensor_trust_profile", []),
        )
