"""
Shared application state for the Partenit Analyzer backend.

Holds in-memory buffers for decisions, trust state, and policies
so that the demo and live guard tester work without a persistent database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from partenit.agent_guard import AgentGuard
from partenit.core.models import DecisionPacket, TrustState
from partenit.decision_log import DecisionLogger
from partenit.decision_log.storage import LocalFileStorage


class AppState:
    """Singleton-like container for shared backend state."""

    def __init__(self) -> None:
        self.guard = AgentGuard()
        self.logger = DecisionLogger()
        self.storage: LocalFileStorage | None = None
        self.trust_states: dict[str, TrustState] = {}
        self.active_policy_path: Path | None = None
        self._active_policies_raw: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Policy management
    # ------------------------------------------------------------------

    def load_policies_from(self, path: Path | str) -> int:
        path = Path(path)
        n = self.guard.load_policies(path)
        self.active_policy_path = path
        bundle = self.guard._bundle  # noqa: SLF001
        if bundle:
            self._active_policies_raw = [r.model_dump() for r in bundle.rules]
        return n

    def get_active_policies(self) -> list[dict[str, Any]]:
        return self._active_policies_raw

    # ------------------------------------------------------------------
    # Decision access
    # ------------------------------------------------------------------

    def recent_packets(self, limit: int = 50, offset: int = 0) -> list[DecisionPacket]:
        all_packets = self.logger.recent(500)
        return all_packets[offset : offset + limit]

    def get_packet(self, packet_id: str) -> DecisionPacket | None:
        for p in self.logger.recent(500):
            if p.packet_id == packet_id:
                return p
        return None

    # ------------------------------------------------------------------
    # Trust state
    # ------------------------------------------------------------------

    def update_trust(self, sensor_id: str, state: TrustState) -> None:
        self.trust_states[sensor_id] = state

    def get_trust_states(self) -> list[TrustState]:
        return list(self.trust_states.values())


# Module-level singleton
_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
    return _state
