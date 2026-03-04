"""
partenit-log CLI

Commands:
    partenit-log verify ./decisions/
    partenit-log report ./decisions/ --from 2025-01-01 --output report.md
    partenit-log inspect <packet_id>
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


def _cmd_verify(args: argparse.Namespace) -> int:
    from partenit.decision_log.archive import DecisionArchive

    archive = DecisionArchive(args.path)
    packets = archive.query()
    result = archive.verify_chain(packets)

    print(f"Verified {result.total} packets: {result.valid} valid, {result.tampered_count} tampered")
    if result.tampered:
        print("\nTampered packets:")
        for pid in result.tampered:
            print(f"  - {pid}")
        return 1
    print("OK: all packets verified")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from partenit.decision_log.archive import DecisionArchive

    archive = DecisionArchive(args.path)

    time_from = None
    time_to = None
    if args.from_date:
        try:
            time_from = datetime.strptime(args.from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"ERROR: invalid --from date '{args.from_date}' (expected YYYY-MM-DD)", file=sys.stderr)
            return 1
    if args.to_date:
        try:
            time_to = datetime.strptime(args.to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"ERROR: invalid --to date '{args.to_date}' (expected YYYY-MM-DD)", file=sys.stderr)
            return 1

    packets = archive.query(time_from=time_from, time_to=time_to)
    report = archive.to_audit_report(packets)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output} ({len(packets)} packets)")
    else:
        print(report)
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    from partenit.decision_log.archive import DecisionArchive
    import json

    archive = DecisionArchive(args.storage_dir)
    packet = archive.get(args.packet_id)

    if not packet:
        print(f"ERROR: packet '{args.packet_id}' not found in {args.storage_dir}", file=sys.stderr)
        return 1

    data = packet.model_dump(mode="json")
    print(json.dumps(data, indent=2, default=str))

    # Verify fingerprint
    valid = packet.compute_fingerprint() == packet.fingerprint
    print(f"\nFingerprint: {'✓ VALID' if valid else '⚠ TAMPERED'}")
    return 0 if valid else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="partenit-log",
        description="Partenit Decision Log CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # verify
    p_verify = sub.add_parser("verify", help="Verify integrity of all decision packets")
    p_verify.add_argument("path", help="Path to decisions directory")

    # report
    p_report = sub.add_parser("report", help="Generate audit report")
    p_report.add_argument("path", help="Path to decisions directory")
    p_report.add_argument("--from", dest="from_date", help="Start date YYYY-MM-DD")
    p_report.add_argument("--to", dest="to_date", help="End date YYYY-MM-DD")
    p_report.add_argument("--output", "-o", help="Output file path (default: stdout)")

    # inspect
    p_inspect = sub.add_parser("inspect", help="Inspect a specific packet")
    p_inspect.add_argument("packet_id", help="Packet ID to inspect")
    p_inspect.add_argument(
        "--storage-dir", default="./decisions/", help="Decisions directory"
    )

    args = parser.parse_args()
    handlers = {
        "verify": _cmd_verify,
        "report": _cmd_report,
        "inspect": _cmd_inspect,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
