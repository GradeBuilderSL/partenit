"""Scenario run endpoints."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

_scenario_results: list[dict[str, Any]] = []


class RunScenarioRequest(BaseModel):
    scenario_yaml: str
    with_guard: bool = True
    seed: int = 42


def _safe_json(value: Any) -> Any:
    """Recursively convert a dataclass / dict / list to a JSON-safe structure.

    Handles:
    - float("inf") / float("-inf") / float("nan") → None
    - tuple → list
    - dataclass → dict (recursive)
    - dict / list → recursive
    """
    if isinstance(value, float):
        if math.isinf(value) or math.isnan(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: _safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(i) for i in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _safe_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    return value


@router.post("/run", summary="Run a scenario from inline YAML")
def run_scenario(req: RunScenarioRequest) -> dict[str, Any]:
    try:
        from partenit.safety_bench.scenario import ScenarioRunner
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="partenit-safety-bench not installed",
        ) from exc

    runner = ScenarioRunner()
    try:
        config = runner.load_str(req.scenario_yaml)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid scenario YAML: {exc}") from exc

    result = runner.run(config, with_guard=req.with_guard, seed=req.seed)
    summary = _safe_json(result)
    _scenario_results.append(summary)
    return summary


@router.get("/results", summary="List all scenario run results")
def list_results() -> dict[str, Any]:
    return {"count": len(_scenario_results), "results": _scenario_results}
