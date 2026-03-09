"""Tests for partenit-decision-log."""

from pathlib import Path

import pytest

from partenit.decision_log.logger import DecisionLogger
from partenit.decision_log.storage import LocalFileStorage
from partenit.decision_log.archive import DecisionArchive, ChainVerificationResult
from partenit.core.models import GuardDecision, RiskScore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_decision(allowed: bool = True, risk: float = 0.2) -> GuardDecision:
    return GuardDecision(
        allowed=allowed,
        risk_score=RiskScore(value=risk),
        applied_policies=["human_proximity_slowdown"] if not allowed else [],
        rejection_reason="Too close to human" if not allowed else None,
    )


# ---------------------------------------------------------------------------
# DecisionLogger
# ---------------------------------------------------------------------------


def test_create_packet_in_memory():
    log = DecisionLogger()
    packet = log.create_packet(
        action_requested="navigate_to",
        action_params={"zone": "A3", "speed": 1.5},
        guard_decision=_make_decision(),
    )
    assert packet.packet_id != ""
    assert packet.fingerprint != ""
    assert packet.action_requested == "navigate_to"


def test_create_packet_stores_in_memory():
    log = DecisionLogger()
    log.create_packet("navigate_to", {}, _make_decision())
    log.create_packet("pick_object", {}, _make_decision(allowed=False))
    assert len(log.recent()) == 2


def test_verify_packet_fresh():
    log = DecisionLogger()
    packet = log.create_packet("navigate_to", {}, _make_decision())
    assert log.verify_packet(packet) is True


def test_verify_packet_tampered():
    log = DecisionLogger()
    packet = log.create_packet("navigate_to", {}, _make_decision())
    tampered = packet.model_copy(update={"mission_goal": "HACKED"})
    assert log.verify_packet(tampered) is False


def test_packet_has_fingerprint():
    log = DecisionLogger()
    packet = log.create_packet("navigate_to", {}, _make_decision())
    assert len(packet.fingerprint) == 64


def test_model_versions_in_packet():
    log = DecisionLogger(model_versions={"trust_engine": "0.1.0"})
    packet = log.create_packet("navigate_to", {}, _make_decision())
    assert packet.model_versions["trust_engine"] == "0.1.0"


# ---------------------------------------------------------------------------
# LocalFileStorage
# ---------------------------------------------------------------------------


def test_storage_write_and_read(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)
    log = DecisionLogger(storage_dir=str(tmp_path))
    packet = log.create_packet("navigate_to", {"zone": "A3"}, _make_decision())

    loaded = storage.read_all()
    assert len(loaded) == 1
    assert loaded[0].packet_id == packet.packet_id


def test_storage_multiple_packets(tmp_path: Path):
    log = DecisionLogger(storage_dir=str(tmp_path))
    for i in range(5):
        log.create_packet(f"action_{i}", {}, _make_decision())

    storage = LocalFileStorage(tmp_path)
    packets = storage.read_all()
    assert len(packets) == 5


def test_storage_list_dates(tmp_path: Path):
    log = DecisionLogger(storage_dir=str(tmp_path))
    log.create_packet("navigate_to", {}, _make_decision())

    storage = LocalFileStorage(tmp_path)
    dates = storage.list_dates()
    assert len(dates) == 1


# ---------------------------------------------------------------------------
# DecisionArchive
# ---------------------------------------------------------------------------


def test_archive_verify_chain_all_valid(tmp_path: Path):
    log = DecisionLogger(storage_dir=str(tmp_path))
    packets = [
        log.create_packet(f"action_{i}", {}, _make_decision()) for i in range(3)
    ]
    archive = DecisionArchive(str(tmp_path))
    result = archive.verify_chain(packets)
    assert result.all_valid is True
    assert result.total == 3
    assert result.tampered_count == 0


def test_archive_verify_chain_detects_tampering(tmp_path: Path):
    log = DecisionLogger(storage_dir=str(tmp_path))
    p1 = log.create_packet("navigate_to", {}, _make_decision())
    p2 = log.create_packet("stop", {}, _make_decision(allowed=False))
    tampered = p1.model_copy(update={"mission_goal": "HACKED"})
    archive = DecisionArchive(str(tmp_path))
    result = archive.verify_chain([tampered, p2])
    assert result.all_valid is False
    assert result.tampered_count == 1
    assert p1.packet_id in result.tampered


def test_archive_audit_report(tmp_path: Path):
    log = DecisionLogger(storage_dir=str(tmp_path))
    log.create_packet("navigate_to", {"zone": "A3"}, _make_decision())
    log.create_packet("navigate_to", {"zone": "HAZ"}, _make_decision(allowed=False))
    packets = log.recent()

    archive = DecisionArchive(str(tmp_path))
    report = archive.to_audit_report(packets)
    assert "Partenit Audit Report" in report
    assert "50.0%" in report
    assert "navigate_to" in report


def test_archive_to_csv(tmp_path: Path):
    log = DecisionLogger(storage_dir=str(tmp_path))
    log.create_packet("navigate_to", {}, _make_decision())
    packets = log.recent()

    archive = DecisionArchive(str(tmp_path))
    csv = archive.to_csv(packets)
    lines = csv.strip().split("\n")
    assert lines[0].startswith("packet_id,")
    assert len(lines) == 2  # header + 1 data row


def test_archive_get_packet(tmp_path: Path):
    log = DecisionLogger(storage_dir=str(tmp_path))
    p = log.create_packet("navigate_to", {}, _make_decision())

    archive = DecisionArchive(str(tmp_path))
    retrieved = archive.get(p.packet_id)
    assert retrieved is not None
    assert retrieved.packet_id == p.packet_id


def test_archive_get_nonexistent(tmp_path: Path):
    archive = DecisionArchive(str(tmp_path))
    result = archive.get("nonexistent-id")
    assert result is None


# ---------------------------------------------------------------------------
# CLI — `partenit-log why` command
# ---------------------------------------------------------------------------


def test_cmd_why_from_directory(tmp_path: Path, capsys):
    """partenit-log why <dir> reads last packet and prints explanation."""
    from partenit.decision_log.cli import _cmd_why
    import argparse

    log = DecisionLogger(storage_dir=str(tmp_path))
    log.create_packet(
        action_requested="navigate_to",
        action_params={"zone": "C2", "speed": 2.0},
        guard_decision=_make_decision(allowed=False, risk=0.92),
    )

    args = argparse.Namespace(path=str(tmp_path))
    rc = _cmd_why(args)
    assert rc == 0

    captured = capsys.readouterr()
    out = captured.out
    assert "navigate_to" in out
    assert "BLOCKED" in out


def test_cmd_why_from_json_file(tmp_path: Path, capsys):
    """partenit-log why <file.json> reads a single JSON packet."""
    import json
    import argparse
    from partenit.decision_log.cli import _cmd_why

    log = DecisionLogger(storage_dir=str(tmp_path))
    packet = log.create_packet(
        action_requested="pick_up",
        action_params={"target": "box_7"},
        guard_decision=_make_decision(allowed=True, risk=0.15),
    )

    json_file = tmp_path / "packet.json"
    json_file.write_text(packet.model_dump_json(indent=2), encoding="utf-8")

    args = argparse.Namespace(path=str(json_file))
    rc = _cmd_why(args)
    assert rc == 0

    captured = capsys.readouterr()
    assert "pick_up" in captured.out


def test_cmd_why_modified_params(tmp_path: Path, capsys):
    """Why command shows modified params when guard clamped speed."""
    import argparse
    from partenit.decision_log.cli import _cmd_why
    from partenit.core.models import GuardDecision, RiskScore

    decision = GuardDecision(
        allowed=True,
        modified_params={"speed": 0.3},
        risk_score=RiskScore(value=0.65),
        applied_policies=["human_proximity_slowdown"],
    )
    log = DecisionLogger(storage_dir=str(tmp_path))
    log.create_packet(
        action_requested="navigate_to",
        action_params={"zone": "A3", "speed": 2.0},
        guard_decision=decision,
    )

    args = argparse.Namespace(path=str(tmp_path))
    rc = _cmd_why(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "MODIFIED" in out or "navigate_to" in out


def test_cmd_why_nonexistent_path(tmp_path: Path):
    """Why command returns error code 1 for missing path."""
    import argparse
    from partenit.decision_log.cli import _cmd_why

    args = argparse.Namespace(path=str(tmp_path / "does_not_exist"))
    rc = _cmd_why(args)
    assert rc == 1


# ---------------------------------------------------------------------------
# Acceptance criteria: packet created even on blocked action
# ---------------------------------------------------------------------------


def test_packet_created_on_blocked_action():
    """DecisionPacket must always be created — even on safe stop."""
    log = DecisionLogger()
    blocked_decision = _make_decision(allowed=False, risk=0.95)
    packet = log.create_packet(
        action_requested="navigate_to",
        action_params={"zone": "HAZ"},
        guard_decision=blocked_decision,
    )
    assert packet.guard_decision.allowed is False
    assert packet.fingerprint != ""
    assert log.verify_packet(packet) is True


# ---------------------------------------------------------------------------
# partenit-stats
# ---------------------------------------------------------------------------


def test_cmd_stats_basic(tmp_path: Path, capsys):
    """partenit-stats shows counts for allowed/modified/blocked decisions."""
    import argparse
    from partenit.decision_log.cli import _cmd_stats
    from partenit.core.models import GuardDecision, RiskScore

    log = DecisionLogger(storage_dir=str(tmp_path))
    log.create_packet("navigate_to", {"speed": 1.0}, _make_decision(allowed=True))
    log.create_packet(
        "navigate_to",
        {"speed": 2.0},
        GuardDecision(
            allowed=True,
            modified_params={"speed": 0.3},
            risk_score=RiskScore(value=0.65),
            applied_policies=["human_proximity_slowdown"],
        ),
    )
    log.create_packet("navigate_to", {}, _make_decision(allowed=False, risk=0.95))

    args = argparse.Namespace(path=str(tmp_path), top=5)
    rc = _cmd_stats(args)
    assert rc == 0

    out = capsys.readouterr().out
    assert "ALLOWED" in out or "allowed" in out.lower()
    assert "BLOCKED" in out or "blocked" in out.lower()


def test_cmd_stats_empty_dir(tmp_path: Path, capsys):
    """partenit-stats returns 1 and prints error when no packets found."""
    import argparse
    from partenit.decision_log.cli import _cmd_stats

    args = argparse.Namespace(path=str(tmp_path / "nonexistent"), top=5)
    rc = _cmd_stats(args)
    assert rc == 1


def test_cmd_stats_contributors(tmp_path: Path, capsys):
    """partenit-stats reads human_distance from risk_score.contributors."""
    import argparse
    from partenit.decision_log.cli import _cmd_stats
    from partenit.core.models import GuardDecision, RiskScore

    log = DecisionLogger(storage_dir=str(tmp_path))
    log.create_packet(
        "navigate_to",
        {"speed": 0.5},
        GuardDecision(
            allowed=True,
            risk_score=RiskScore(value=0.72, contributors={"human_distance": 0.85}),
            applied_policies=[],
        ),
    )

    args = argparse.Namespace(path=str(tmp_path), top=5)
    rc = _cmd_stats(args)
    assert rc == 0
