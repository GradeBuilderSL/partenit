"""
DecisionLogger — creates, fingerprints, and stores DecisionPackets.

Every guard decision must be logged here before execution.
There is no code path that skips logging (acceptance criteria).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from partenit.core.models import DecisionFingerprint, DecisionPacket, GuardDecision
from partenit.decision_log.storage import DecisionStorage, LocalFileStorage

logger = logging.getLogger(__name__)


class DecisionLogger:
    """
    Creates and stores DecisionPackets with cryptographic fingerprints.

    Usage:
        log = DecisionLogger(storage_dir="./decisions/")
        packet = log.create_packet(
            action_requested="navigate_to",
            action_params={"zone": "A3", "speed": 1.5},
            guard_decision=decision,
        )
        assert log.verify_packet(packet)  # Always True if untampered
    """

    def __init__(
        self,
        storage_dir: str | None = None,
        model_versions: dict[str, str] | None = None,
        storage: DecisionStorage | None = None,
    ) -> None:
        """
        Args:
            storage_dir: Where to persist JSONL files.
                         If None and no ``storage`` is given, packets are only
                         kept in memory.
            model_versions: Version tags for audit trail.
                            e.g. {'trust_engine': '0.1.0', 'policy_dsl': '0.1.0'}
            storage: Explicit storage backend (overrides storage_dir).
                     Pass an InMemoryStorage for tests, or any DecisionStorage
                     implementation for custom backends (S3, PostgreSQL, …).
        """
        if storage is not None:
            self._storage: DecisionStorage | None = storage
        elif storage_dir:
            self._storage = LocalFileStorage(storage_dir)
        else:
            self._storage = None
        self._model_versions = model_versions or {}
        self._in_memory: list[DecisionPacket] = []

    def create_packet(
        self,
        action_requested: str,
        action_params: dict[str, Any],
        guard_decision: GuardDecision,
        mission_goal: str = "",
        observation_hashes: list[str] | None = None,
        world_state_hash: str | None = None,
        policy_bundle_version: str | None = None,
        latency_ms: dict[str, float] | None = None,
        conflicts_resolved: list[dict[str, Any]] | None = None,
        violations_checked: list[str] | None = None,
    ) -> DecisionPacket:
        """
        Create, fingerprint, and store a DecisionPacket.

        Returns the stored packet (with fingerprint filled in).
        """
        packet = DecisionPacket(
            action_requested=action_requested,
            action_params=action_params,
            guard_decision=guard_decision,
            mission_goal=mission_goal,
            observation_hashes=observation_hashes or [],
            world_state_hash=world_state_hash,
            policy_bundle_version=policy_bundle_version,
            model_versions=self._model_versions,
            latency_ms=latency_ms or {},
            conflicts_resolved=conflicts_resolved or [],
            violations_checked=violations_checked or [],
        )

        # Compute and attach fingerprint
        fp = packet.compute_fingerprint()
        packet = packet.model_copy(update={"fingerprint": fp})

        self._store(packet)
        return packet

    def verify_packet(self, packet: DecisionPacket) -> bool:
        """
        Verify packet integrity.

        Returns True if the packet's current fingerprint matches its content.
        Always True for freshly created packets, False if tampered.
        """
        return packet.compute_fingerprint() == packet.fingerprint

    def get_fingerprint(self, packet: DecisionPacket) -> DecisionFingerprint:
        """Return a detached DecisionFingerprint for a packet."""
        return DecisionFingerprint(
            fingerprint=packet.fingerprint,
            packet_id=packet.packet_id,
        )

    def recent(self, n: int = 10) -> list[DecisionPacket]:
        """Return the N most recent packets from in-memory buffer."""
        return list(self._in_memory[-n:])

    def _store(self, packet: DecisionPacket) -> None:
        """Persist packet and keep in memory."""
        self._in_memory.append(packet)
        if self._storage:
            self._storage.write(packet)
