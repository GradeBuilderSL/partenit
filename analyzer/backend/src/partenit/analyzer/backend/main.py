"""
Partenit Analyzer — FastAPI backend.

Run:
    uvicorn partenit.analyzer.backend.main:app --reload --port 8000

Or via CLI entry point:
    partenit-analyzer

Prometheus metrics are available at GET /metrics if prometheus_client is installed.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from partenit.analyzer.backend.routes import decisions, guard, policies, scenarios, trust
from partenit.analyzer.backend.state import get_state
from partenit.analyzer.backend.metrics import metrics_response

# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

DEFAULT_POLICY_PATH = os.environ.get(
    "PARTENIT_POLICY_PATH",
    str(
        Path(__file__).resolve().parents[6]
        / "examples"
        / "warehouse"
        / "policies.yaml"
    ),
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    state = get_state()
    policy_path = Path(DEFAULT_POLICY_PATH)
    if policy_path.exists():
        n = state.load_policies_from(policy_path)
        print(f"[Partenit] Loaded {n} policies from {policy_path}")
    else:
        print(f"[Partenit] Policy path not found: {policy_path}")
        print("[Partenit] Use POST /policies/load to load policies.")
    yield


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Partenit Analyzer API",
    description=(
        "REST API for querying guard decisions, trust state, active policies, "
        "and running live safety checks. Serves the Partenit Analyzer web UI."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(decisions.router)
app.include_router(trust.router)
app.include_router(policies.router)
app.include_router(guard.router)
app.include_router(scenarios.router)


# ---------------------------------------------------------------------------
# Prometheus metrics endpoint (optional — requires prometheus_client)
# ---------------------------------------------------------------------------

@app.get("/metrics", tags=["observability"], include_in_schema=False)
def metrics() -> Response:
    """
    Prometheus metrics endpoint.

    Available metrics:
    - partenit_guard_decisions_total  (labels: allowed, action, modified)
    - partenit_guard_latency_ms       (histogram)
    - partenit_risk_score             (gauge)
    - partenit_sensor_trust_level     (gauge, label: sensor_id)
    - partenit_policy_fires_total     (counter, label: rule_id)

    Returns 501 if prometheus_client is not installed.
    """
    result = metrics_response()
    if result is None:
        return Response(
            content=b"prometheus_client not installed. pip install prometheus_client",
            status_code=501,
            media_type="text/plain",
        )
    body, content_type = result
    return Response(content=body, media_type=content_type)


# ---------------------------------------------------------------------------
# Health + root
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
def health() -> dict[str, Any]:
    state = get_state()
    return {
        "status": "ok",
        "decisions_in_memory": len(state.logger.recent(500)),
        "active_policies": len(state.get_active_policies()),
        "trust_sensors": len(state.get_trust_states()),
    }


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "name": "Partenit Analyzer API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    uvicorn.run(
        "partenit.analyzer.backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
