"""Decision log endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from partenit.analyzer.backend.state import get_state

router = APIRouter(prefix="/decisions", tags=["decisions"])


@router.get("", summary="List recent decisions")
def list_decisions(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    state = get_state()
    packets = state.recent_packets(limit=limit, offset=offset)
    return {
        "total": len(state.logger.recent(500)),
        "limit": limit,
        "offset": offset,
        "items": [p.model_dump() for p in packets],
    }


@router.get("/{packet_id}", summary="Get a single decision packet")
def get_decision(packet_id: str) -> dict[str, Any]:
    state = get_state()
    packet = state.get_packet(packet_id)
    if packet is None:
        raise HTTPException(status_code=404, detail=f"Packet '{packet_id}' not found")
    verified = state.logger.verify_packet(packet)
    data = packet.model_dump()
    data["_verified"] = verified
    return data


@router.get("/{packet_id}/verify", summary="Verify a packet fingerprint")
def verify_decision(packet_id: str) -> dict[str, Any]:
    state = get_state()
    packet = state.get_packet(packet_id)
    if packet is None:
        raise HTTPException(status_code=404, detail=f"Packet '{packet_id}' not found")
    verified = state.logger.verify_packet(packet)
    return {
        "packet_id": packet_id,
        "fingerprint": packet.fingerprint,
        "verified": verified,
    }
