"""
partenit-safety-bench — safety scenario simulation and benchmarking.

Run built-in scenarios to compare robot behavior with and without guard.
"""

from partenit.safety_bench.robot import MockRobot
from partenit.safety_bench.scenario import ScenarioResult, ScenarioRunner
from partenit.safety_bench.world import MockWorld, WorldObject

__all__ = ["ScenarioRunner", "ScenarioResult", "MockWorld", "WorldObject", "MockRobot"]
