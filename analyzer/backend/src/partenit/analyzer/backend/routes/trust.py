"""Trust state endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from partenit.analyzer.backend.state import get_state

router = APIRouter(prefix="/trust", tags=["trust"])


@router.get("/current", summary="Get current trust state for all sensors")
def get_trust_current() -> dict[str, Any]:
    state = get_state()
    trust_states = state.get_trust_states()
    return {
        "count": len(trust_states),
        "sensors": [t.model_dump() for t in trust_states],
    }
