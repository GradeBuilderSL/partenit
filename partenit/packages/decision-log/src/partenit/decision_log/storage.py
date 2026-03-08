"""
Storage backends for DecisionPackets.

DecisionStorage (ABC) — common interface for all backends.
LocalFileStorage     — JSONL files on local filesystem (default).
InMemoryStorage      — in-memory only; useful for testing and ephemeral runs.

Future backends (S3, PostgreSQL) implement DecisionStorage without changing
any code in DecisionLogger.
"""

from __future__ import annotations

import abc
import logging
from datetime import UTC, datetime
from pathlib import Path

import jsonlines

from partenit.core.models import DecisionPacket

logger = logging.getLogger(__name__)


class DecisionStorage(abc.ABC):
    """Abstract storage backend for DecisionPackets."""

    @abc.abstractmethod
    def write(self, packet: DecisionPacket) -> None:
        """Persist a single packet."""

    @abc.abstractmethod
    def read_all(self, date: datetime | None = None) -> list[DecisionPacket]:
        """Return all packets for the given date (or today)."""

    def list_dates(self) -> list[str]:
        """Return list of date strings for which data exists."""
        return []


class InMemoryStorage(DecisionStorage):
    """
    Ephemeral in-memory storage.  No disk writes.

    Suitable for:
    - Unit tests that must not touch the filesystem.
    - Short-lived bench runs where packets are consumed immediately.
    """

    def __init__(self) -> None:
        self._packets: list[DecisionPacket] = []

    def write(self, packet: DecisionPacket) -> None:
        self._packets.append(packet)

    def read_all(self, date: datetime | None = None) -> list[DecisionPacket]:
        if date is None:
            return list(self._packets)
        target = date.date()
        return [p for p in self._packets if p.timestamp.date() == target]

    def __len__(self) -> int:
        return len(self._packets)


class LocalFileStorage(DecisionStorage):
    """
    Stores DecisionPackets in JSONL files on the local filesystem.

    One file per day: decisions/2025-01-15.jsonl
    Each line is one complete DecisionPacket JSON object.

    Designed for:
    - Air-gapped robots
    - Edge nodes with limited storage
    - Audit trail that can be verified offline
    """

    def __init__(self, storage_dir: str | Path) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def write(self, packet: DecisionPacket) -> None:
        """Append packet to today's JSONL file."""
        path = self._path_for(packet.timestamp)
        data = packet.model_dump(mode="json")
        try:
            with jsonlines.open(path, mode="a") as writer:
                writer.write(data)
        except Exception as e:
            logger.error("Failed to write DecisionPacket %s: %s", packet.packet_id, e)

    def read_all(self, date: datetime | None = None) -> list[DecisionPacket]:
        """
        Read all packets from the given date's file.
        Defaults to today.
        """
        path = self._path_for(date or datetime.now(UTC))
        if not path.exists():
            return []
        packets: list[DecisionPacket] = []
        try:
            with jsonlines.open(path) as reader:
                for item in reader:
                    try:
                        packets.append(DecisionPacket.model_validate(item))
                    except Exception as e:
                        logger.warning("Skipping malformed packet: %s", e)
        except Exception as e:
            logger.error("Failed to read %s: %s", path, e)
        return packets

    def read_range(self, start: datetime, end: datetime) -> list[DecisionPacket]:
        """Read all packets in the [start, end] date range."""
        packets: list[DecisionPacket] = []
        for path in sorted(self.storage_dir.glob("*.jsonl")):
            try:
                file_date = datetime.strptime(path.stem, "%Y-%m-%d").replace(tzinfo=UTC)
                if start.date() <= file_date.date() <= end.date():
                    packets.extend(self.read_all(file_date))
            except ValueError:
                continue
        # Filter by exact timestamp
        return [p for p in packets if start <= p.timestamp.replace(tzinfo=UTC) <= end]

    def list_dates(self) -> list[str]:
        """Return list of dates (YYYY-MM-DD) for which log files exist."""
        return sorted(p.stem for p in self.storage_dir.glob("*.jsonl"))

    def _path_for(self, dt: datetime) -> Path:
        date_str = dt.strftime("%Y-%m-%d")
        return self.storage_dir / f"{date_str}.jsonl"
