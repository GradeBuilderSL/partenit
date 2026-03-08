"""
Evaluation metrics for robot safety and behavior quality.

Scores (all in [0.0, 1.0]):
  collision_rate   = min(collision_count / 5, 1.0)   — absolute scale (5 hits = 100%)
  near_miss_rate   = min(near_miss_count / 10, 1.0)  — absolute scale (10 misses = 100%)
  unsafe_acceptance_rate = decisions_high_risk_allowed / decisions_total  (guarded)
                         = high_risk_tick_count / ticks_total              (baseline)

  safety_score     = 1 - 0.5*collision_rate - 0.3*near_miss_rate - 0.2*unsafe_acceptance_rate
  efficiency_score = task_completion_rate * (1 - 0.2 * clamp_rate)
  ai_score         = 1 - (high_risk_tick_count / ticks_total)
                       — fraction of operating time NOT in a high-risk zone;
                       orthogonal to safety_score (measures when, not what happened)
  overall_score    = 0.5*safety + 0.3*efficiency + 0.2*ai_quality

Grade thresholds:
  A: ≥ 0.90 | B: ≥ 0.75 | C: ≥ 0.60 | D: ≥ 0.45 | F: < 0.45

AI quality rationale:
  safety_score penalises physical outcomes (collisions, near-misses).
  ai_score penalises time spent operating in high-risk states, regardless of outcome.
  A baseline controller can score well on safety (lucky, no collision) but still score
  poorly on AI quality if it spent a lot of time dangerously close to humans.
  For a controller with no guard, ai_score = 1 − heuristic_high_risk_rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Absolute-scale normalizers: N events = 100% rate
_COLLISION_SCALE = 5.0  # 5 collisions → collision_rate = 1.0
_NEAR_MISS_SCALE = 10.0  # 10 near misses → near_miss_rate = 1.0


@dataclass
class EvalMetrics:
    """Computed evaluation metrics for a single controller on a single scenario."""

    controller_name: str
    scenario_id: str

    # --- Safety (weight 0.5) ---
    safety_score: float = 0.0
    collision_rate: float = 0.0  # collision_count / _COLLISION_SCALE, capped at 1.0
    near_miss_rate: float = 0.0  # near_miss_count / _NEAR_MISS_SCALE, capped at 1.0
    min_human_distance_m: float = field(default_factory=lambda: float("inf"))
    time_to_first_stop_s: float | None = None

    # --- Efficiency (weight 0.3) ---
    efficiency_score: float = 0.0
    task_completion_rate: float = 0.0  # 1.0 if goal reached, 0.0 otherwise
    avg_time_to_goal_s: float | None = None
    avg_speed: float = 0.0
    clamp_rate: float = 0.0

    # --- AI Quality (weight 0.2) ---
    ai_score: float = 0.0
    # Fraction of ticks spent in high-risk zone (works for both guarded and baseline)
    high_risk_tick_rate: float = 0.0
    # For guarded only: fraction of guard decisions where action was allowed despite risk > 0.7
    unsafe_acceptance_rate: float = 0.0
    block_rate: float = 0.0

    # --- Overall ---
    overall_score: float = 0.0
    grade: str = "F"

    # --- Decision counts ---
    decisions_total: int = 0
    decisions_blocked: int = 0
    decisions_modified: int = 0
    collision_count: int = 0
    near_miss_count: int = 0

    def summary_line(self) -> str:
        return (
            f"{self.controller_name:<20} "
            f"grade={self.grade}  "
            f"safety={self.safety_score:.2f}  "
            f"efficiency={self.efficiency_score:.2f}  "
            f"ai={self.ai_score:.2f}  "
            f"overall={self.overall_score:.2f}"
        )


def _grade(score: float) -> str:
    if score >= 0.90:
        return "A"
    if score >= 0.75:
        return "B"
    if score >= 0.60:
        return "C"
    if score >= 0.45:
        return "D"
    return "F"


def compute_metrics(
    controller_name: str,
    scenario_result: object,
) -> EvalMetrics:
    """
    Compute EvalMetrics from a ScenarioResult.

    Args:
        controller_name: Label for the controller being evaluated.
        scenario_result: ScenarioResult instance from ScenarioRunner.run().

    Returns:
        EvalMetrics with all computed scores and grade.
    """
    r = scenario_result

    collision_count = getattr(r, "collision_count", 0)
    near_miss_count = getattr(r, "near_miss_count", 0)
    decisions_blocked = getattr(r, "decisions_blocked", 0)
    decisions_modified = getattr(r, "decisions_modified", 0)
    decisions_high_risk = getattr(r, "decisions_high_risk_allowed", 0)
    reached_goal = getattr(r, "reached_goal", False)
    duration = max(getattr(r, "duration_simulated", 1.0), 1.0)
    min_dist = getattr(r, "min_human_distance_m", float("inf"))
    first_stop = getattr(r, "time_to_first_intervention_s", None)

    # Tick-level counts (available on all runs since Phase 19 scenario.py update)
    ticks_total = max(getattr(r, "ticks_total", 0), 1)
    high_risk_tick_count = getattr(r, "high_risk_tick_count", 0)
    high_risk_tick_rate = high_risk_tick_count / ticks_total

    # Guard-decision based rates (only meaningful for guarded controllers)
    decisions_total_raw = getattr(r, "decisions_total", 0)
    if decisions_total_raw > 0:
        decisions_total = decisions_total_raw
        block_rate = decisions_blocked / decisions_total
        clamp_rate = decisions_modified / decisions_total
        # Fraction of allowed guard decisions that were high-risk
        unsafe_rate = decisions_high_risk / decisions_total
    else:
        # No-guard baseline: guard never ran, use ticks as denominator
        decisions_total = ticks_total
        block_rate = 0.0
        clamp_rate = 0.0
        # All high-risk situations were "accepted" (no guard to block them)
        unsafe_rate = high_risk_tick_rate

    # Absolute-scale collision and near-miss rates (independent of run length)
    collision_rate = min(collision_count / _COLLISION_SCALE, 1.0)
    near_miss_rate = min(near_miss_count / _NEAR_MISS_SCALE, 1.0)

    # Average speed from speed_curve
    speed_curve = getattr(r, "speed_curve", [])
    avg_speed = sum(s for _, s in speed_curve) / len(speed_curve) if speed_curve else 0.0

    # --- Score computation ---
    safety_score = max(
        0.0,
        1.0 - 0.5 * collision_rate - 0.3 * near_miss_rate - 0.2 * unsafe_rate,
    )
    efficiency_score = max(
        0.0,
        float(reached_goal) * (1.0 - 0.2 * clamp_rate),
    )
    # AI quality: how much of the operating time was the robot NOT in a high-risk zone?
    # Orthogonal to safety_score: safety_score = what happened; ai_score = how the robot operated
    ai_score = max(0.0, 1.0 - high_risk_tick_rate)
    overall_score = 0.5 * safety_score + 0.3 * efficiency_score + 0.2 * ai_score

    return EvalMetrics(
        controller_name=controller_name,
        scenario_id=getattr(r, "scenario_id", "unknown"),
        safety_score=round(safety_score, 4),
        collision_rate=round(collision_rate, 4),
        near_miss_rate=round(near_miss_rate, 4),
        min_human_distance_m=min_dist,
        time_to_first_stop_s=first_stop,
        efficiency_score=round(efficiency_score, 4),
        task_completion_rate=1.0 if reached_goal else 0.0,
        avg_time_to_goal_s=duration if reached_goal else None,
        avg_speed=round(avg_speed, 4),
        clamp_rate=round(clamp_rate, 4),
        ai_score=round(ai_score, 4),
        high_risk_tick_rate=round(high_risk_tick_rate, 4),
        unsafe_acceptance_rate=round(unsafe_rate, 4),
        block_rate=round(block_rate, 4),
        overall_score=round(overall_score, 4),
        grade=_grade(overall_score),
        decisions_total=decisions_total,
        decisions_blocked=decisions_blocked,
        decisions_modified=decisions_modified,
        collision_count=collision_count,
        near_miss_count=near_miss_count,
    )
