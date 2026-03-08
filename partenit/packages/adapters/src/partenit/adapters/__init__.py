"""
partenit-adapters — hardware-agnostic robot adapters.

Switch adapters with a single line. Everything else stays identical.
"""

from partenit.adapters.base import RobotAdapter
from partenit.adapters.mock import MockRobotAdapter

__all__ = ["RobotAdapter", "MockRobotAdapter"]

try:
    from partenit.adapters.http import CircuitBreaker, HTTPRobotAdapter

    __all__ += ["HTTPRobotAdapter", "CircuitBreaker"]
except ImportError:
    pass  # httpx not installed
