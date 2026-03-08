"""
HTTPRobotAdapter — adapter for any robot exposing the Partenit HTTP API.

Vendor contract (OpenAPI spec in /schemas/robot-adapter-api.yaml):
    GET  /partenit/observations  ->  StructuredObservation[]
    POST /partenit/command       <-  GuardDecision
    GET  /partenit/health        ->  {status, robot_id, timestamp}

Includes an optional CircuitBreaker to protect against unresponsive robots.
Inspired by _old/robot_connector/connector.py circuit-breaker pattern.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from enum import StrEnum

from partenit.adapters.base import RobotAdapter
from partenit.core.models import GuardDecision, StructuredObservation

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitState(StrEnum):
    CLOSED = "closed"       # Normal — all calls pass through
    OPEN = "open"           # Too many failures — calls rejected immediately
    HALF_OPEN = "half_open" # Cooldown elapsed — one probe call allowed


class CircuitBreaker:
    """
    Simple circuit breaker for HTTP robot calls.

    States:
        CLOSED   → normal operation; failures increment counter
        OPEN     → after failure_threshold reached; calls rejected until cooldown
        HALF_OPEN → after cooldown; one probe call; success → CLOSED, failure → OPEN

    Usage:
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
        if cb.allow():
            try:
                result = do_http_call()
                cb.record_success()
            except Exception:
                cb.record_failure()
                raise
        else:
            raise RuntimeError("Circuit open — robot unreachable")
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if self._opened_at is not None:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self.cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
        return self._state

    def allow(self) -> bool:
        """Return True if the call should proceed."""
        s = self.state
        return s in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Call after a successful HTTP request."""
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        """Call after a failed HTTP request."""
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "CircuitBreaker OPEN after %d failures (cooldown %ss)",
                self._failures,
                self.cooldown_seconds,
            )

    def reset(self) -> None:
        """Manually reset to CLOSED state."""
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class HTTPRobotAdapter(RobotAdapter):
    """
    Adapter for any robot or fleet system that implements the Partenit
    robot-adapter HTTP API.

    Usage:
        adapter = HTTPRobotAdapter(base_url="http://192.168.1.100")
        obs = adapter.get_observations()
        adapter.send_decision(decision)

    With circuit breaker (auto-enabled by default):
        adapter = HTTPRobotAdapter(
            base_url="http://192.168.1.100",
            circuit_breaker=CircuitBreaker(failure_threshold=5, cooldown_seconds=60),
        )
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 2.0,
        headers: dict[str, str] | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        """
        Args:
            base_url: Robot base URL (e.g. "http://192.168.1.100")
            timeout: Request timeout in seconds.
            headers: Optional HTTP headers (e.g. for auth tokens).
            circuit_breaker: Optional CircuitBreaker instance. Defaults to
                CircuitBreaker(failure_threshold=3, cooldown_seconds=30).
                Pass ``circuit_breaker=None`` explicitly to disable.
        """
        if not _HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for HTTPRobotAdapter. "
                "Install with: pip install partenit-adapters[http]"
            )
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers=headers or {},
        )
        # None → use default CircuitBreaker; pass a custom instance to tune thresholds
        self._cb: CircuitBreaker = (
            circuit_breaker if circuit_breaker is not None else CircuitBreaker()
        )

    def _call(self, fn, *args, **kwargs):
        """Execute fn with circuit-breaker protection."""
        if not self._cb.allow():
            raise RuntimeError(
                f"CircuitBreaker OPEN — robot at {self.base_url} is unreachable. "
                f"State will reset after cooldown."
            )
        try:
            result = fn(*args, **kwargs)
            self._cb.record_success()
            return result
        except Exception:
            self._cb.record_failure()
            raise

    def get_observations(self) -> list[StructuredObservation]:
        """Fetch observations from GET /partenit/observations."""
        try:
            resp = self._call(self._client.get, "/partenit/observations")
            resp.raise_for_status()
            items = resp.json()
            return [StructuredObservation.model_validate(item) for item in items]
        except Exception as e:
            logger.error("HTTPRobotAdapter.get_observations failed: %s", e)
            return []

    def send_decision(self, decision: GuardDecision) -> bool:
        """Send decision to POST /partenit/command."""
        try:
            payload = decision.model_dump(mode="json")
            resp = self._call(self._client.post, "/partenit/command", json=payload)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("HTTPRobotAdapter.send_decision failed: %s", e)
            return False

    def get_health(self) -> dict:
        """Fetch health from GET /partenit/health."""
        try:
            resp = self._call(self._client.get, "/partenit/health")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("HTTPRobotAdapter.get_health failed: %s", e)
            return {
                "status": "unreachable",
                "robot_id": "unknown",
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def is_simulation(self) -> bool:
        return False

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Access the circuit breaker for monitoring or manual reset."""
        return self._cb

    def close(self) -> None:
        """Close the HTTP client connection pool."""
        self._client.close()

    def __enter__(self) -> HTTPRobotAdapter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
