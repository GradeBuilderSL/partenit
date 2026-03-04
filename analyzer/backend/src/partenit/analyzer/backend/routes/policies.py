"""Policy management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from partenit.analyzer.backend.state import get_state

router = APIRouter(prefix="/policies", tags=["policies"])


class LoadPoliciesRequest(BaseModel):
    path: str


@router.get("/active", summary="List currently active policy rules")
def get_active_policies() -> dict[str, Any]:
    state = get_state()
    policies = state.get_active_policies()
    return {
        "count": len(policies),
        "path": str(state.active_policy_path) if state.active_policy_path else None,
        "rules": policies,
    }


@router.post("/load", summary="Load policies from a file or directory path")
def load_policies(req: LoadPoliciesRequest) -> dict[str, Any]:
    state = get_state()
    try:
        n = state.load_policies_from(req.path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"loaded": n, "path": req.path}
