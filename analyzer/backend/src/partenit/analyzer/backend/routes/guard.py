"""Live guard check endpoint — send action + context, receive GuardDecision."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from partenit.analyzer.backend.state import get_state
from partenit.analyzer.backend.metrics import record_guard_decision

router = APIRouter(prefix="/guard", tags=["guard"])


class GuardCheckRequest(BaseModel):
    action: str
    params: dict[str, Any] = {}
    context: dict[str, Any] = {}
    log_decision: bool = True


@router.post("/check", summary="Check an action against the current policies")
def guard_check(req: GuardCheckRequest) -> dict[str, Any]:
    state = get_state()
    decision = state.guard.check_action(
        action=req.action,
        params=req.params,
        context=req.context,
    )

    # Emit Prometheus metrics (no-op if prometheus_client not installed)
    record_guard_decision(
        allowed=decision.allowed,
        action=req.action,
        modified=decision.modified_params is not None,
        latency_ms=decision.latency_ms,
        risk_value=decision.risk_score.value,
        applied_policies=decision.applied_policies,
    )

    packet = None
    if req.log_decision:
        packet = state.logger.create_packet(
            action_requested=req.action,
            action_params=req.params,
            guard_decision=decision,
        )

    result: dict[str, Any] = {"decision": decision.model_dump()}
    if packet:
        result["packet_id"] = packet.packet_id
        result["fingerprint"] = packet.fingerprint
        result["verified"] = state.logger.verify_packet(packet)

    return result
