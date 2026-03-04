"""
DecisionArchive — query, verify, and report on stored DecisionPackets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from partenit.core.models import DecisionPacket
from partenit.decision_log.storage import LocalFileStorage

logger = logging.getLogger(__name__)


@dataclass
class ChainVerificationResult:
    """Result of verifying a sequence of DecisionPackets."""

    total: int
    valid: int
    tampered: list[str] = field(default_factory=list)

    @property
    def all_valid(self) -> bool:
        return len(self.tampered) == 0

    @property
    def tampered_count(self) -> int:
        return len(self.tampered)


class DecisionArchive:
    """
    Query and verify stored DecisionPackets.

    Usage:
        archive = DecisionArchive(storage_dir="./decisions/")
        packets = archive.query(time_from=..., time_to=...)
        result = archive.verify_chain(packets)
        print(archive.to_audit_report(packets))
    """

    def __init__(self, storage_dir: str) -> None:
        self._storage = LocalFileStorage(storage_dir)

    def get(self, packet_id: str) -> DecisionPacket | None:
        """Retrieve a specific packet by ID from today's log."""
        all_packets = self._storage.read_all()
        for p in all_packets:
            if p.packet_id == packet_id:
                return p
        return None

    def query(
        self,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> list[DecisionPacket]:
        """Return packets in the given time range."""
        if time_from is None:
            time_from = datetime(2020, 1, 1, tzinfo=timezone.utc)
        if time_to is None:
            time_to = datetime(2100, 1, 1, tzinfo=timezone.utc)
        return self._storage.read_range(time_from, time_to)

    def verify_chain(self, packets: list[DecisionPacket]) -> ChainVerificationResult:
        """
        Verify the integrity of each packet in the list.

        Returns a ChainVerificationResult with tampered packet IDs.
        """
        tampered: list[str] = []
        for p in packets:
            expected = p.compute_fingerprint()
            if expected != p.fingerprint:
                tampered.append(p.packet_id)
                logger.warning("Tampered packet detected: %s", p.packet_id)
        return ChainVerificationResult(
            total=len(packets),
            valid=len(packets) - len(tampered),
            tampered=tampered,
        )

    def to_audit_report(self, packets: list[DecisionPacket]) -> str:
        """Generate a markdown audit report from a list of packets."""
        if not packets:
            return "# Audit Report\n\nNo packets found.\n"

        total = len(packets)
        allowed = sum(1 for p in packets if p.guard_decision.allowed)
        blocked = total - allowed
        verification = self.verify_chain(packets)

        lines = [
            "# Partenit Audit Report",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"**Packets:** {total}",
            f"**Allowed:** {allowed}  **Blocked:** {blocked}",
            f"**Block rate:** {blocked / total * 100:.1f}%",
            f"**Integrity:** {'✓ All packets verified' if verification.all_valid else f'⚠ {verification.tampered_count} tampered'}",
            "",
            "## Decisions",
            "",
            "| Timestamp | Action | Allowed | Risk | Policies |",
            "|-----------|--------|---------|------|----------|",
        ]
        for p in packets[:50]:  # Limit table to 50 rows
            ts = p.timestamp.strftime("%Y-%m-%dT%H:%M:%S")
            allowed_str = "✓" if p.guard_decision.allowed else "✗"
            risk = f"{p.guard_decision.risk_score.value:.2f}"
            policies = ", ".join(p.guard_decision.applied_policies[:3])
            lines.append(f"| {ts} | {p.action_requested} | {allowed_str} | {risk} | {policies} |")

        if total > 50:
            lines.append(f"\n_... {total - 50} more packets not shown_")

        if verification.tampered:
            lines.extend([
                "",
                "## Tampered Packets",
                "",
                *[f"- `{pid}`" for pid in verification.tampered],
            ])

        return "\n".join(lines) + "\n"

    def to_csv(self, packets: list[DecisionPacket]) -> str:
        """Export packets to CSV format."""
        lines = ["packet_id,timestamp,action,allowed,risk_score,applied_policies,latency_ms"]
        for p in packets:
            policies = "|".join(p.guard_decision.applied_policies)
            total_latency = p.latency_ms.get("total", p.guard_decision.latency_ms)
            lines.append(
                f"{p.packet_id},"
                f"{p.timestamp.isoformat()},"
                f"{p.action_requested},"
                f"{p.guard_decision.allowed},"
                f"{p.guard_decision.risk_score.value:.4f},"
                f"{policies},"
                f"{total_latency:.1f}"
            )
        return "\n".join(lines) + "\n"
