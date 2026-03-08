"""
MockRobot — simulated robot for safety bench scenarios.

Moves toward a goal and responds to guard decisions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class MockRobot:
    """
    Simulated robot that navigates from start to goal.

    The robot moves at `current_speed` m/s toward `goal`.
    When the guard clamps speed, it slows down.
    When the guard blocks, it stops.
    """

    start_x: float = 0.0
    start_y: float = 0.0
    goal_x: float = 10.0
    goal_y: float = 0.0
    initial_speed: float = 1.0

    x: float = field(init=False)
    y: float = field(init=False)
    current_speed: float = field(init=False)
    stopped: bool = field(init=False, default=False)
    events: list[dict] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.x = self.start_x
        self.y = self.start_y
        self.current_speed = self.initial_speed

    def step(self, dt: float, guard_decision=None) -> None:
        """
        Advance robot one step.

        If guard_decision is provided:
        - If not allowed → stop
        - If modified_params has 'speed' → apply speed clamp
        - If allowed with no speed clamp → restore to initial_speed
        """
        if guard_decision is not None:
            if not guard_decision.allowed:
                self.stopped = True
                self.events.append({"type": "stop", "reason": guard_decision.rejection_reason})
                return
            mp = guard_decision.modified_params
            if mp and "speed" in mp:
                new_speed = float(mp["speed"])
                if new_speed < self.current_speed:
                    self.events.append(
                        {
                            "type": "slowdown",
                            "from": self.current_speed,
                            "to": new_speed,
                        }
                    )
                self.current_speed = new_speed
            else:
                # Guard allows without speed restriction → restore to initial
                if self.current_speed < self.initial_speed:
                    self.current_speed = self.initial_speed

        self.stopped = False

        # Move toward goal
        dx = self.goal_x - self.x
        dy = self.goal_y - self.y
        dist = math.sqrt(dx**2 + dy**2)
        if dist < 0.01:
            return  # Reached goal

        speed = min(self.current_speed, dist / dt) if dt > 0 else self.current_speed
        self.x += (dx / dist) * speed * dt
        self.y += (dy / dist) * speed * dt

    @property
    def distance_to_goal(self) -> float:
        return math.sqrt((self.goal_x - self.x) ** 2 + (self.goal_y - self.y) ** 2)

    @property
    def reached_goal(self) -> bool:
        return self.distance_to_goal < 0.1

    def reset(self) -> None:
        self.x = self.start_x
        self.y = self.start_y
        self.current_speed = self.initial_speed
        self.stopped = False
        self.events.clear()
