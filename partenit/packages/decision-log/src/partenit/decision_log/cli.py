"""
partenit-log CLI

Commands:
    partenit-log verify ./decisions/
    partenit-log report ./decisions/ --from 2025-01-01 --output report.md
    partenit-log inspect <packet_id>
    partenit-log replay ./decisions/           (alias: partenit-replay)
    partenit-log replay decision.json --output replay.html

partenit-record CLI (alias for session management):
    partenit-record list
    partenit-record show <session_name>
    partenit-record export <session_name>
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


def _cmd_replay(args: argparse.Namespace) -> int:
    """Replay decisions from a file or directory in rich terminal or HTML format."""
    from partenit.decision_log.storage import LocalFileStorage, InMemoryStorage
    from partenit.decision_log.archive import DecisionArchive
    import json

    path = Path(args.path)
    packets = []

    if path.is_file() and path.suffix in (".json", ".jsonl"):
        # Single file — load packets from it
        if path.suffix == ".jsonl":
            storage = InMemoryStorage()
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        from partenit.core.models import DecisionPacket
                        packets.append(DecisionPacket.model_validate_json(line))
        else:
            from partenit.core.models import DecisionPacket
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                packets = [DecisionPacket.model_validate(d) for d in data]
            else:
                packets = [DecisionPacket.model_validate(data)]
    elif path.is_dir():
        archive = DecisionArchive(str(path))
        packets = archive.query()
    else:
        print(f"ERROR: path does not exist or unsupported format: {path}", file=sys.stderr)
        return 1

    if not packets:
        print("No decision packets found.")
        return 0

    if args.output:
        # HTML replay
        html = _render_replay_html(packets, title=path.name)
        Path(args.output).write_text(html, encoding="utf-8")
        print(f"Replay written to {args.output} ({len(packets)} packets)")
        return 0

    # Terminal replay (rich if available, fallback to plain)
    _print_replay_terminal(packets, source=str(path))
    return 0


def _print_replay_terminal(packets: list, source: str) -> None:
    """Print decision replay in terminal using rich (if available) or plain text."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text
        _rich_replay(packets, source)
    except ImportError:
        _plain_replay(packets, source)


def _rich_replay(packets: list, source: str) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print(f"\n[bold cyan]Decision Replay[/] — {source} ([yellow]{len(packets)}[/] packets)\n")

    blocked = sum(1 for p in packets if not p.guard_decision.allowed)
    modified = sum(1 for p in packets if p.guard_decision.modified_params)
    allowed_clean = len(packets) - blocked - modified

    table = Table(show_header=True, header_style="bold", border_style="dim")
    table.add_column("Time", style="dim", width=8)
    table.add_column("Status", width=10)
    table.add_column("Action", width=14)
    table.add_column("Risk", width=6)
    table.add_column("Policies / Reason", style="dim")

    for p in packets:
        d = p.guard_decision
        ts = p.timestamp.strftime("%H:%M:%S")
        risk_val = f"{d.risk_score.value:.2f}" if d.risk_score else "—"

        if not d.allowed:
            status = "[red]BLOCKED [/]"
            detail = d.rejection_reason or ""
        elif d.modified_params:
            status = "[yellow]MODIFIED[/]"
            detail = ", ".join(d.applied_policies) if d.applied_policies else ""
        else:
            status = "[green]ALLOWED [/]"
            detail = ""

        table.add_row(ts, status, p.action_requested, risk_val, detail)

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/] {len(packets)} total | "
        f"[red]{blocked} blocked[/] | [yellow]{modified} modified[/] | [green]{allowed_clean} allowed[/]\n"
    )


def _plain_replay(packets: list, source: str) -> None:
    print(f"\nDecision Replay — {source} ({len(packets)} packets)")
    print("─" * 60)
    for p in packets:
        d = p.guard_decision
        ts = p.timestamp.strftime("%H:%M:%S")
        risk_val = f"{d.risk_score.value:.2f}" if d.risk_score else "---"
        status = "BLOCKED " if not d.allowed else ("MODIFIED" if d.modified_params else "ALLOWED ")
        policies = ", ".join(d.applied_policies) if d.applied_policies else ""
        print(f" {ts}  [{status}] {p.action_requested:<14} risk={risk_val}  {policies}")

    blocked = sum(1 for p in packets if not p.guard_decision.allowed)
    modified = sum(1 for p in packets if p.guard_decision.modified_params)
    print(f"\nSummary: {len(packets)} total | {blocked} blocked | {modified} modified | {len(packets)-blocked-modified} allowed\n")


def _render_replay_html(packets: list, title: str = "Decision Replay") -> str:
    """Generate a minimal HTML replay page."""
    rows = []
    for p in packets:
        d = p.guard_decision
        ts = p.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        risk_val = f"{d.risk_score.value:.2f}" if d.risk_score else "—"
        if not d.allowed:
            row_cls = "blocked"
            status = "BLOCKED"
            detail = d.rejection_reason or ""
        elif d.modified_params:
            row_cls = "modified"
            status = "MODIFIED"
            detail = ", ".join(d.applied_policies) if d.applied_policies else ""
        else:
            row_cls = "allowed"
            status = "ALLOWED"
            detail = ""
        rows.append(
            f'<tr class="{row_cls}"><td>{ts}</td><td>{status}</td>'
            f'<td>{p.action_requested}</td><td>{risk_val}</td><td>{detail}</td></tr>'
        )

    rows_html = "\n".join(rows)
    blocked = sum(1 for p in packets if not p.guard_decision.allowed)
    modified = sum(1 for p in packets if p.guard_decision.modified_params)

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Partenit — {title}</title>
<style>
body{{font-family:monospace;background:#0f1117;color:#e2e8f0;margin:2rem;}}
h1{{color:#60a5fa;}}
.summary{{margin:1rem 0;color:#94a3b8;}}
table{{border-collapse:collapse;width:100%;max-width:1000px;}}
th{{background:#1e293b;padding:.5rem 1rem;text-align:left;}}
td{{padding:.4rem 1rem;border-bottom:1px solid #1e293b;}}
.blocked{{background:#2d1b1b;}}
.modified{{background:#2d2510;}}
.allowed{{background:#0f1117;}}
.blocked td:nth-child(2){{color:#f87171;font-weight:bold;}}
.modified td:nth-child(2){{color:#fbbf24;font-weight:bold;}}
.allowed td:nth-child(2){{color:#34d399;}}
</style></head>
<body>
<h1>Decision Replay — {title}</h1>
<p class="summary">{len(packets)} packets | {blocked} blocked | {modified} modified | {len(packets)-blocked-modified} allowed</p>
<table>
<tr><th>Timestamp</th><th>Status</th><th>Action</th><th>Risk</th><th>Policies / Reason</th></tr>
{rows_html}
</table>
</body></html>"""


def _cmd_record_list(args: argparse.Namespace) -> int:
    """List recorded sessions in the decisions directory."""
    base = Path(args.dir)
    if not base.exists():
        print(f"No decisions directory found at {base}")
        return 0

    sessions = sorted([d for d in base.iterdir() if d.is_dir()])
    files = sorted(base.glob("*.jsonl"))

    if not sessions and not files:
        print(f"No sessions found in {base}")
        return 0

    print(f"\nDecision sessions in {base}:")
    print("─" * 40)
    for s in sessions:
        n = len(list(s.glob("*.jsonl")))
        print(f"  {s.name}/   ({n} log files)")
    for f in files:
        print(f"  {f.name}")
    print()
    return 0


def _cmd_record_show(args: argparse.Namespace) -> int:
    """Show summary of a named session."""
    from partenit.decision_log.archive import DecisionArchive

    session_dir = Path(args.dir) / args.session_name
    if not session_dir.exists():
        print(f"ERROR: session '{args.session_name}' not found in {args.dir}", file=sys.stderr)
        return 1

    archive = DecisionArchive(str(session_dir))
    packets = archive.query()

    if not packets:
        print(f"Session '{args.session_name}': no packets found")
        return 0

    blocked = sum(1 for p in packets if not p.guard_decision.allowed)
    modified = sum(1 for p in packets if p.guard_decision.modified_params)
    t_start = min(p.timestamp for p in packets)
    t_end = max(p.timestamp for p in packets)

    print(f"\nSession: {args.session_name}")
    print(f"  Packets  : {len(packets)}")
    print(f"  Period   : {t_start.strftime('%Y-%m-%d %H:%M:%S')} → {t_end.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Blocked  : {blocked} ({100*blocked/len(packets):.0f}%)")
    print(f"  Modified : {modified} ({100*modified/len(packets):.0f}%)")
    print(f"  Allowed  : {len(packets)-blocked-modified}")
    print()
    return 0


def _cmd_record_export(args: argparse.Namespace) -> int:
    """Export a session to a single JSON file."""
    import json
    from partenit.decision_log.archive import DecisionArchive

    session_dir = Path(args.dir) / args.session_name
    if not session_dir.exists():
        print(f"ERROR: session '{args.session_name}' not found in {args.dir}", file=sys.stderr)
        return 1

    archive = DecisionArchive(str(session_dir))
    packets = archive.query()

    output = args.output or f"{args.session_name}_export.json"
    data = [p.model_dump(mode="json") for p in packets]
    Path(output).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"Exported {len(packets)} packets to {output}")
    return 0


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

    # replay
    p_replay = sub.add_parser("replay", help="Replay decision timeline in terminal or HTML")
    p_replay.add_argument("path", help="Path to decisions directory or .jsonl/.json file")
    p_replay.add_argument("--output", "-o", help="Output HTML file (default: terminal)")

    args = parser.parse_args()
    handlers = {
        "verify": _cmd_verify,
        "report": _cmd_report,
        "inspect": _cmd_inspect,
        "replay": _cmd_replay,
    }
    sys.exit(handlers[args.command](args))


def replay_main() -> None:
    """Entry point for 'partenit-replay' command."""
    parser = argparse.ArgumentParser(
        prog="partenit-replay",
        description="Replay Partenit decision timeline",
    )
    parser.add_argument("path", help="Path to decisions directory or .jsonl/.json file")
    parser.add_argument("--output", "-o", help="Output HTML file (default: terminal)")
    args = parser.parse_args()
    sys.exit(_cmd_replay(args))


def record_main() -> None:
    """Entry point for 'partenit-record' command."""
    parser = argparse.ArgumentParser(
        prog="partenit-record",
        description="Manage Partenit decision recording sessions",
    )
    parser.add_argument("--dir", default="./decisions/", help="Base decisions directory")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all recorded sessions")

    p_show = sub.add_parser("show", help="Show session summary")
    p_show.add_argument("session_name", help="Session name")

    p_export = sub.add_parser("export", help="Export session to JSON")
    p_export.add_argument("session_name", help="Session name")
    p_export.add_argument("--output", "-o", help="Output file (default: <session>_export.json)")

    args = parser.parse_args()
    handlers = {
        "list": _cmd_record_list,
        "show": _cmd_record_show,
        "export": _cmd_record_export,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
