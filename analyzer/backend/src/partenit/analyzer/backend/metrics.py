"""
Prometheus metrics for the Partenit Analyzer backend.

Optional dependency: prometheus_client.
If not installed, all functions are no-ops and /metrics returns 501.

Usage:
    from partenit.analyzer.backend.metrics import (
        record_guard_decision,
        record_sensor_trust,
        REGISTRY,
    )
"""

from __future__ import annotations

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    REGISTRY = CollectorRegistry(auto_describe=True)

    _decisions = Counter(
        "partenit_guard_decisions_total",
        "Total guard evaluations",
        ["allowed", "action", "modified"],
        registry=REGISTRY,
    )

    _latency = Histogram(
        "partenit_guard_latency_ms",
        "Guard evaluation latency in milliseconds",
        buckets=[0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500],
        registry=REGISTRY,
    )

    _risk_score = Gauge(
        "partenit_risk_score",
        "Last computed risk score [0,1]",
        registry=REGISTRY,
    )

    _trust = Gauge(
        "partenit_sensor_trust_level",
        "Per-sensor trust level [0,1]",
        ["sensor_id"],
        registry=REGISTRY,
    )

    _policy_fires = Counter(
        "partenit_policy_fires_total",
        "Number of times a policy rule fired",
        ["rule_id"],
        registry=REGISTRY,
    )

    _METRICS_AVAILABLE = True

except ImportError:
    REGISTRY = None
    _METRICS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public helpers (always safe to call — no-op when prometheus unavailable)
# ---------------------------------------------------------------------------


def record_guard_decision(
    *,
    allowed: bool,
    action: str,
    modified: bool,
    latency_ms: float,
    risk_value: float,
    applied_policies: list[str],
) -> None:
    if not _METRICS_AVAILABLE:
        return
    _decisions.labels(
        allowed=str(allowed).lower(),
        action=action,
        modified=str(modified).lower(),
    ).inc()
    _latency.observe(latency_ms)
    _risk_score.set(risk_value)
    for rule_id in applied_policies:
        _policy_fires.labels(rule_id=rule_id).inc()


def record_sensor_trust(sensor_id: str, trust_value: float) -> None:
    if not _METRICS_AVAILABLE:
        return
    _trust.labels(sensor_id=sensor_id).set(trust_value)


def metrics_response() -> tuple[bytes, str] | None:
    """
    Return (body_bytes, content_type) for the /metrics endpoint,
    or None if prometheus_client is not installed.
    """
    if not _METRICS_AVAILABLE:
        return None
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
