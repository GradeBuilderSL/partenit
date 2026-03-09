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
from datetime import UTC, datetime
from pathlib import Path


def _cmd_verify(args: argparse.Namespace) -> int:
    from partenit.decision_log.archive import DecisionArchive

    archive = DecisionArchive(args.path)
    packets = archive.query()
    result = archive.verify_chain(packets)

    print(
        f"Verified {result.total} packets: {result.valid} valid, {result.tampered_count} tampered"
    )
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
            time_from = datetime.strptime(args.from_date, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            print(
                f"ERROR: invalid --from date '{args.from_date}' (expected YYYY-MM-DD)",
                file=sys.stderr,
            )
            return 1
    if args.to_date:
        try:
            time_to = datetime.strptime(args.to_date, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            print(
                f"ERROR: invalid --to date '{args.to_date}' (expected YYYY-MM-DD)", file=sys.stderr
            )
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
    import json

    from partenit.decision_log.archive import DecisionArchive

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
    import json

    from partenit.decision_log.archive import DecisionArchive
    from partenit.decision_log.storage import InMemoryStorage

    path = Path(args.path)
    packets = []

    if path.is_file() and path.suffix in (".json", ".jsonl"):
        # Single file — load packets from it
        if path.suffix == ".jsonl":
            InMemoryStorage()
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
        import rich  # noqa: F401

        _rich_replay(packets, source)
    except ImportError:
        _plain_replay(packets, source)


def _rich_replay(packets: list, source: str) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print(
        f"\n[bold cyan]Decision Replay[/] — {source} ([yellow]{len(packets)}[/] packets)\n"
    )

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
    print(
        f"\nSummary: {len(packets)} total | {blocked} blocked | {modified} modified | {len(packets) - blocked - modified} allowed\n"
    )


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
            f"<td>{p.action_requested}</td><td>{risk_val}</td><td>{detail}</td></tr>"
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
<p class="summary">{len(packets)} packets | {blocked} blocked | {modified} modified | {len(packets) - blocked - modified} allowed</p>
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
    print(
        f"  Period   : {t_start.strftime('%Y-%m-%d %H:%M:%S')} → {t_end.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print(f"  Blocked  : {blocked} ({100 * blocked / len(packets):.0f}%)")
    print(f"  Modified : {modified} ({100 * modified / len(packets):.0f}%)")
    print(f"  Allowed  : {len(packets) - blocked - modified}")
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


def _cmd_why(args: argparse.Namespace) -> int:
    """Explain a single decision in plain English."""
    import json

    from partenit.core.models import DecisionPacket

    path = Path(args.path)

    # Load packet
    packet: DecisionPacket | None = None
    if path.is_file() and path.suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                # Take first packet from list
                packet = DecisionPacket.model_validate(data[0])
            else:
                packet = DecisionPacket.model_validate(data)
        except Exception as exc:
            print(f"ERROR: cannot read packet from {path}: {exc}", file=sys.stderr)
            return 1
    elif path.is_file() and path.suffix == ".jsonl":
        # Take last packet from JSONL
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            print("ERROR: empty file", file=sys.stderr)
            return 1
        packet = DecisionPacket.model_validate_json(lines[-1])
    elif path.is_dir():
        # Search directory for packet by partial ID match
        from partenit.decision_log.archive import DecisionArchive

        archive = DecisionArchive(str(path))
        packets = archive.query()
        if not packets:
            print(f"No packets found in {path}", file=sys.stderr)
            return 1
        packet = packets[-1]
    else:
        print(f"ERROR: path does not exist: {path}", file=sys.stderr)
        return 1

    _print_why(packet)
    return 0


def _print_why(packet: object) -> None:
    """Render a human-readable explanation of a DecisionPacket."""
    try:
        import rich as _rich  # noqa: F401

        _rich_why(packet)
        return
    except ImportError:
        pass

    # Plain fallback
    d = packet.guard_decision
    ts = packet.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    status = "BLOCKED" if not d.allowed else ("MODIFIED" if d.modified_params else "ALLOWED")
    risk = f"{d.risk_score.value:.2f}" if d.risk_score else "—"

    print(f"\n{'─' * 58}")
    print("  Decision Explanation")
    print(f"{'─' * 58}")
    print(f"  Action : {packet.action_requested}({_fmt_params(packet.action_params)})")
    print(f"  Time   : {ts}")
    print(f"  Status : {status}   Risk: {risk}")
    print()

    if not d.allowed:
        print("  Why BLOCKED:")
        if d.rejection_reason:
            print(f"    → {d.rejection_reason}")
        for policy in d.applied_policies:
            print(f"    → Rule fired: {policy}")
    elif d.modified_params:
        print("  Why MODIFIED:")
        for policy in d.applied_policies:
            print(f"    → Rule fired: {policy}")
        print("  Modified params:")
        for k, v in d.modified_params.items():
            orig = packet.action_params.get(k, "?")
            if orig != v:
                print(f"    {k}: {orig} → {v}")
            else:
                print(f"    {k}: {v}")
    else:
        print("  Decision: ALLOWED — no policies fired, risk within threshold.")

    if d.risk_score and d.risk_score.contributors:
        print("\n  Risk contributors:")
        for feat, weight in sorted(d.risk_score.contributors.items(), key=lambda x: -x[1]):
            bar = "█" * int(weight * 20)
            print(f"    {feat:<30} {weight:.2f}  {bar}")

    fp_valid = packet.compute_fingerprint() == packet.fingerprint
    print(f"\n  Fingerprint: {'✓ VALID' if fp_valid else '⚠ TAMPERED'}")
    print(f"{'─' * 58}\n")


def _rich_why(packet: object) -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = Console()
    d = packet.guard_decision
    ts = packet.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    risk = f"{d.risk_score.value:.2f}" if d.risk_score else "—"

    if not d.allowed:
        status_str = "[bold red]● BLOCKED[/]"
        border = "red"
    elif d.modified_params:
        status_str = "[bold yellow]● MODIFIED[/]"
        border = "yellow"
    else:
        status_str = "[bold green]● ALLOWED[/]"
        border = "green"

    lines = Text()
    lines.append("Action : ", style="dim")
    lines.append(f"{packet.action_requested}({_fmt_params(packet.action_params)})\n", style="bold")
    lines.append(f"Time   : {ts}\n", style="dim")
    lines.append("Status : ")
    lines.append_text(Text.from_markup(f"{status_str}   "))
    lines.append(f"Risk score: {risk}\n")

    if not d.allowed:
        lines.append("\nWhy BLOCKED:\n", style="bold")
        if d.rejection_reason:
            lines.append(f"  → {d.rejection_reason}\n", style="red")
        for policy in d.applied_policies:
            lines.append("  → Rule fired: ", style="dim")
            lines.append(f"{policy}\n", style="yellow")
    elif d.modified_params:
        lines.append("\nWhy MODIFIED:\n", style="bold")
        for policy in d.applied_policies:
            lines.append("  → Rule fired: ", style="dim")
            lines.append(f"{policy}\n", style="yellow")
        lines.append("\nParameter changes:\n", style="bold")
        for k, v in d.modified_params.items():
            orig = packet.action_params.get(k, "?")
            if orig != v:
                lines.append(f"  {k}: ", style="dim")
                lines.append(f"{orig}", style="red strike")
                lines.append(" → ")
                lines.append(f"{v}\n", style="green")
            else:
                lines.append(f"  {k}: {v}\n", style="dim")
    else:
        lines.append("\nNo policies fired. Risk within safe threshold.\n", style="green dim")

    if d.risk_score and d.risk_score.contributors:
        lines.append("\nRisk contributors:\n", style="bold")
        for feat, weight in sorted(d.risk_score.contributors.items(), key=lambda x: -x[1]):
            bar = "█" * int(weight * 16)
            color = "red" if weight > 0.6 else "yellow" if weight > 0.3 else "green"
            lines.append(f"  {feat:<28} ", style="dim")
            lines.append(f"{weight:.2f}  ", style=color)
            lines.append(f"{bar}\n", style=color)

    fp_valid = packet.compute_fingerprint() == packet.fingerprint
    fp_text = "✓ VALID" if fp_valid else "⚠ TAMPERED"
    fp_style = "green dim" if fp_valid else "bold red"
    lines.append("\nFingerprint: ", style="dim")
    lines.append(fp_text, style=fp_style)

    console.print()
    console.print(Panel(lines, title="[bold]Decision Explanation[/]", border_style=border))
    console.print()


def _fmt_params(params: dict) -> str:
    """Format action params as a compact string."""
    if not params:
        return ""
    return ", ".join(f"{k}={v!r}" for k, v in list(params.items())[:4])


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
    p_inspect.add_argument("--storage-dir", default="./decisions/", help="Decisions directory")

    # replay
    p_replay = sub.add_parser("replay", help="Replay decision timeline in terminal or HTML")
    p_replay.add_argument("path", help="Path to decisions directory or .jsonl/.json file")
    p_replay.add_argument("--output", "-o", help="Output HTML file (default: terminal)")

    # why
    p_why = sub.add_parser("why", help="Explain a single decision in plain English")
    p_why.add_argument(
        "path",
        help="Path to a .json packet file, .jsonl log file, or decisions directory",
    )

    # stats
    p_stats = sub.add_parser("stats", help="Statistical summary of guard decisions")
    p_stats.add_argument(
        "path",
        nargs="?",
        default="./decisions/",
        help="Path to decisions directory or file (default: ./decisions/)",
    )
    p_stats.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format: text (default) or json",
    )

    # watch
    p_watch = sub.add_parser("watch", help="Live monitor of guard decisions (tail a directory)")
    p_watch.add_argument(
        "path",
        nargs="?",
        default="./decisions/",
        help="Decisions directory to watch (default: ./decisions/)",
    )
    p_watch.add_argument(
        "--tail",
        type=int,
        default=20,
        metavar="N",
        help="Number of recent rows to show (default: 20)",
    )

    # export
    p_export = sub.add_parser("export", help="Export decision packets to JSON, JSONL, or CSV")
    p_export.add_argument(
        "path",
        nargs="?",
        default="./decisions/",
        help="Path to decisions directory or file (default: ./decisions/)",
    )
    p_export.add_argument(
        "--format",
        "-f",
        choices=["json", "jsonl", "csv"],
        default="json",
        help="Output format: json (default), jsonl, csv",
    )
    p_export.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output file path (default: stdout)",
    )
    p_export.add_argument(
        "--session",
        "-s",
        default=None,
        metavar="NAME",
        help="Export only a specific session subdirectory",
    )

    args = parser.parse_args()
    handlers = {
        "verify": _cmd_verify,
        "report": _cmd_report,
        "inspect": _cmd_inspect,
        "replay": _cmd_replay,
        "why": _cmd_why,
        "stats": _cmd_stats,
        "watch": _cmd_watch,
        "export": _cmd_export,
    }
    sys.exit(handlers[args.command](args))


def why_main() -> None:
    """Entry point for 'partenit-why' command."""
    parser = argparse.ArgumentParser(
        prog="partenit-why",
        description="Explain a Partenit guard decision in plain English",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="./decisions/",
        help="Path to .json packet, .jsonl log, or decisions directory (default: ./decisions/)",
    )
    args = parser.parse_args()
    sys.exit(_cmd_why(args))


def _cmd_watch(args: argparse.Namespace) -> int:
    """Live monitor of guard decisions — tail a decisions directory."""
    import time

    from partenit.core.models import DecisionPacket

    watch_dir = Path(args.path)
    if not watch_dir.exists():
        print(f"ERROR: directory does not exist: {watch_dir}", file=sys.stderr)
        return 1

    try:
        import rich as _rich  # noqa: F401

        _watch_rich(watch_dir, args)
        return 0
    except ImportError:
        pass

    # Plain fallback: tail and print
    print(f"Watching {watch_dir} for new decisions... (Ctrl+C to stop)\n")
    seen_bytes: dict[Path, int] = {}

    try:
        while True:
            for jsonl_file in sorted(watch_dir.rglob("*.jsonl")):
                prev = seen_bytes.get(jsonl_file, 0)
                size = jsonl_file.stat().st_size
                if size > prev:
                    with open(jsonl_file, encoding="utf-8") as f:
                        f.seek(prev)
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    p = DecisionPacket.model_validate_json(line)
                                    d = p.guard_decision
                                    ts = p.timestamp.strftime("%H:%M:%S")
                                    risk = f"{d.risk_score.value:.2f}" if d.risk_score else "---"
                                    status = (
                                        "BLOCKED "
                                        if not d.allowed
                                        else ("MODIFIED" if d.modified_params else "ALLOWED ")
                                    )
                                    policies = (
                                        ", ".join(d.applied_policies) if d.applied_policies else ""
                                    )
                                    print(
                                        f" {ts}  [{status}] {p.action_requested:<16} risk={risk}  {policies}"
                                    )
                                except Exception:
                                    pass
                    seen_bytes[jsonl_file] = size
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def _watch_rich(watch_dir: Path, args: argparse.Namespace) -> None:  # type: ignore[name-defined]
    """Rich TUI live monitor."""
    import time

    from rich.console import Console
    from rich.live import Live
    from rich.table import Table

    from partenit.core.models import DecisionPacket

    console = Console()
    max_rows = getattr(args, "tail", 20)
    session_name = watch_dir.name

    decisions: list[tuple[str, str, str, str, str]] = []  # ts, status, action, risk, detail
    stats = {"total": 0, "blocked": 0, "modified": 0}
    seen_bytes: dict[Path, int] = {}

    def _make_table() -> Table:
        table = Table(
            show_header=True,
            header_style="bold cyan",
            border_style="dim",
            title=f"[bold cyan]Partenit Guard Monitor[/] — {session_name}  "
            f"[dim]total={stats['total']} "
            f"[red]blocked={stats['blocked']}[/] "
            f"[yellow]modified={stats['modified']}[/][/dim]",
            title_justify="left",
        )
        table.add_column("Time", style="dim", width=10)
        table.add_column("Status", width=10)
        table.add_column("Action", width=18)
        table.add_column("Risk", width=6)
        table.add_column("Policies / Reason", style="dim")

        for ts, status, action, risk, detail in decisions[-max_rows:]:
            table.add_row(ts, status, action, risk, detail)

        return table

    def _poll() -> None:
        for jsonl_file in sorted(watch_dir.rglob("*.jsonl")):
            prev = seen_bytes.get(jsonl_file, 0)
            size = jsonl_file.stat().st_size
            if size > prev:
                with open(jsonl_file, encoding="utf-8") as f:
                    f.seek(prev)
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            p = DecisionPacket.model_validate_json(line)
                            d = p.guard_decision
                            ts = p.timestamp.strftime("%H:%M:%S")
                            risk = f"{d.risk_score.value:.2f}" if d.risk_score else "—"
                            if not d.allowed:
                                status = "[bold red]BLOCKED [/]"
                                detail = d.rejection_reason or ""
                            elif d.modified_params:
                                status = "[bold yellow]MODIFIED[/]"
                                detail = ", ".join(d.applied_policies) if d.applied_policies else ""
                            else:
                                status = "[bold green]ALLOWED [/]"
                                detail = ""
                            decisions.append((ts, status, p.action_requested, risk, detail))
                            stats["total"] += 1
                            if not d.allowed:
                                stats["blocked"] += 1
                            elif d.modified_params:
                                stats["modified"] += 1
                        except Exception:
                            pass
                seen_bytes[jsonl_file] = size

    console.print(f"[dim]Watching [bold]{watch_dir}[/] — Ctrl+C to stop[/]\n")

    with Live(_make_table(), console=console, refresh_per_second=2, screen=False) as live:
        try:
            while True:
                _poll()
                live.update(_make_table())
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    console.print("\n[dim]Guard monitor stopped.[/]")


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


def watch_main() -> None:
    """Entry point for 'partenit-watch' command."""
    parser = argparse.ArgumentParser(
        prog="partenit-watch",
        description="Live monitor of Partenit guard decisions",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="./decisions/",
        help="Decisions directory to watch (default: ./decisions/)",
    )
    parser.add_argument(
        "--tail",
        type=int,
        default=20,
        metavar="N",
        help="Number of recent decisions to display (default: 20)",
    )
    args = parser.parse_args()
    sys.exit(_cmd_watch(args))


def _cmd_stats(args: argparse.Namespace) -> int:
    """
    Show a statistical summary of guard decisions in a session/directory.

    Displays status breakdown, top fired policies, risk distribution,
    and fingerprint integrity.
    """
    import json

    from partenit.core.models import DecisionPacket
    from partenit.decision_log.archive import DecisionArchive

    path = Path(args.path)
    packets: list = []

    if path.is_file() and path.suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else [raw]
        packets = [DecisionPacket.model_validate(d) for d in items]
    elif path.is_file() and path.suffix == ".jsonl":
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    packets.append(DecisionPacket.model_validate_json(ln))
    elif path.is_dir():
        archive = DecisionArchive(str(path))
        packets = archive.query()
    else:
        print(f"ERROR: path not found: {path}", file=sys.stderr)
        return 1

    if not packets:
        print("No decision packets found.")
        return 0

    # -- Compute stats --
    n = len(packets)
    n_allowed = sum(
        1 for p in packets if p.guard_decision.allowed and p.guard_decision.modified_params is None
    )
    n_modified = sum(
        1
        for p in packets
        if p.guard_decision.allowed and p.guard_decision.modified_params is not None
    )
    n_blocked = sum(1 for p in packets if not p.guard_decision.allowed)

    # Top policies
    from collections import Counter

    policy_counts: Counter = Counter()
    for p in packets:
        for pol in p.guard_decision.applied_policies or []:
            policy_counts[pol] += 1

    # Risk stats
    risks = [p.guard_decision.risk_score.value for p in packets if p.guard_decision.risk_score]
    risk_mean = sum(risks) / len(risks) if risks else None
    risk_max = max(risks) if risks else None
    risk_p95 = sorted(risks)[int(len(risks) * 0.95)] if len(risks) >= 2 else risk_max

    # Min human distance from features
    distances = []
    for p in packets:
        if p.guard_decision.risk_score and p.guard_decision.risk_score.contributors:
            dist = p.guard_decision.risk_score.contributors.get("human_distance")
            if dist is not None:
                distances.append(float(dist))
    min_dist = min(distances) if distances else None

    # Session duration
    sorted_pkts = sorted(packets, key=lambda p: p.timestamp)
    duration_s: float | None = None
    if len(sorted_pkts) >= 2:
        delta = sorted_pkts[-1].timestamp - sorted_pkts[0].timestamp
        duration_s = delta.total_seconds()

    # Session name
    session_name = path.stem if path.is_file() else path.name

    # Fingerprint verification
    n_valid = sum(1 for p in packets if p.compute_fingerprint() == p.fingerprint)
    n_tampered = n - n_valid

    fmt = getattr(args, "format", "text") or "text"

    if fmt == "json":
        data: dict = {
            "session": session_name,
            "total": n,
            "allowed": n_allowed,
            "modified": n_modified,
            "blocked": n_blocked,
            "risk": {
                "mean": round(risk_mean, 4) if risk_mean is not None else None,
                "p95": round(risk_p95, 4) if risk_p95 is not None else None,
                "max": round(risk_max, 4) if risk_max is not None else None,
            },
            "top_policies": policy_counts.most_common(10),
            "min_human_distance_m": round(min_dist, 4) if min_dist is not None else None,
            "duration_s": round(duration_s, 2) if duration_s is not None else None,
            "fingerprints": {"valid": n_valid, "tampered": n_tampered},
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    _print_stats(
        session_name=session_name,
        n=n,
        n_allowed=n_allowed,
        n_modified=n_modified,
        n_blocked=n_blocked,
        policy_counts=policy_counts,
        risk_mean=risk_mean,
        risk_max=risk_max,
        risk_p95=risk_p95,
        min_dist=min_dist,
        duration_s=duration_s,
        n_valid=n_valid,
        n_tampered=n_tampered,
    )
    return 0


def _print_stats(**kw) -> None:
    try:
        import rich as _rich  # noqa: F401

        _rich_stats(**kw)
    except ImportError:
        _plain_stats(**kw)


def _bar(ratio: float, width: int = 20) -> str:
    filled = round(ratio * width)
    return "█" * filled + "░" * (width - filled)


def _rich_stats(
    session_name,
    n,
    n_allowed,
    n_modified,
    n_blocked,
    policy_counts,
    risk_mean,
    risk_max,
    risk_p95,
    min_dist,
    duration_s,
    n_valid,
    n_tampered,
) -> None:
    from rich.console import Console
    from rich.rule import Rule
    from rich.table import Table

    console = Console()
    console.print()

    # Header
    dur_str = ""
    if duration_s is not None:
        m, s = divmod(int(duration_s), 60)
        dur_str = f"  │  Duration: {m}m {s:02d}s" if m else f"  │  Duration: {s}s"
    console.print(
        Rule(
            f"[bold]Robot Safety Summary[/]  [dim]{session_name}[/]  "
            f"Decisions: [bold]{n}[/]{dur_str}"
        )
    )
    console.print()

    # Status breakdown
    console.print("[bold]Status breakdown:[/]")
    for label, count, color in [
        ("ALLOWED  ", n_allowed, "green"),
        ("MODIFIED ", n_modified, "yellow"),
        ("BLOCKED  ", n_blocked, "red"),
    ]:
        ratio = count / n if n else 0.0
        pct = f"{ratio * 100:5.1f}%"
        bar = _bar(ratio)
        console.print(f"  [{color}]● {label}[/]  {count:4d}  {pct}  [{color}]{bar}[/]")

    # Top policies
    if policy_counts:
        console.print()
        console.print("[bold]Top policies fired:[/]")
        for pol, cnt in policy_counts.most_common(5):
            console.print(f"  [dim]{pol:<40}[/] [bold]{cnt}x[/]")

    # Risk stats
    if risk_mean is not None:
        console.print()
        console.print("[bold]Risk scores:[/]")
        console.print(
            f"  Average: [yellow]{risk_mean:.2f}[/]  │  "
            f"P95: [yellow]{risk_p95:.2f}[/]  │  "
            f"Peak: [red]{risk_max:.2f}[/]"
        )

    # Extra
    if min_dist is not None:
        console.print(f"  Min human distance: [bold]{min_dist:.2f} m[/]")

    # Fingerprints
    console.print()
    fp_color = "green" if n_tampered == 0 else "red"
    fp_icon = "✓" if n_tampered == 0 else "⚠"
    console.print(
        f"[bold]Fingerprints:[/]  [{fp_color}]{fp_icon} {n_valid} valid[/]"
        + (f"  [red]{n_tampered} tampered[/]" if n_tampered else "")
    )

    # Safety grade (simple heuristic, no bench dep)
    if n > 0:
        block_rate = n_blocked / n
        grade = (
            "A"
            if block_rate < 0.01
            else "B"
            if block_rate < 0.05
            else "C"
            if block_rate < 0.1
            else "D"
        )
        grade_color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red"}.get(grade, "red")
        console.print(
            f"  Blocked rate: [{grade_color}]{block_rate:.1%}[/]  │  "
            f"Guard grade (heuristic): [{grade_color}][bold]{grade}[/][/]"
        )

    # Summary line
    console.print()
    table = Table.grid(padding=1)
    table.add_row(
        f"[green]{n_allowed}[/] allowed",
        f"[yellow]{n_modified}[/] modified",
        f"[red]{n_blocked}[/] blocked",
        f"[dim]out of {n} decisions[/]",
    )
    console.print(table)
    console.print()


def _plain_stats(
    session_name,
    n,
    n_allowed,
    n_modified,
    n_blocked,
    policy_counts,
    risk_mean,
    risk_max,
    risk_p95,
    min_dist,
    duration_s,
    n_valid,
    n_tampered,
) -> None:
    sep = "─" * 50
    print(f"\nRobot Safety Summary — {session_name}")
    print(sep)
    if duration_s is not None:
        m, s = divmod(int(duration_s), 60)
        print(f"Duration: {m}m {s:02d}s  |  Decisions: {n}")
    else:
        print(f"Decisions: {n}")
    print()

    print("Status breakdown:")
    for label, count in [
        ("ALLOWED  ", n_allowed),
        ("MODIFIED ", n_modified),
        ("BLOCKED  ", n_blocked),
    ]:
        ratio = count / n if n else 0.0
        print(f"  {label}  {count:4d}  {ratio * 100:5.1f}%  {_bar(ratio, 20)}")

    if policy_counts:
        print("\nTop policies fired:")
        for pol, cnt in policy_counts.most_common(5):
            print(f"  {pol:<40} {cnt}x")

    if risk_mean is not None:
        print(f"\nRisk: avg={risk_mean:.2f}  p95={risk_p95:.2f}  peak={risk_max:.2f}")

    if min_dist is not None:
        print(f"Min human distance: {min_dist:.2f} m")

    fp_status = "OK" if n_tampered == 0 else f"TAMPERED ({n_tampered})"
    print(f"\nFingerprints: {n_valid} valid / {n_tampered} tampered — {fp_status}")

    if n > 0:
        block_rate = n_blocked / n
        grade = (
            "A"
            if block_rate < 0.01
            else "B"
            if block_rate < 0.05
            else "C"
            if block_rate < 0.1
            else "D"
        )
        print(f"Blocked rate: {block_rate:.1%}  |  Guard grade: {grade}")

    print(f"\nSummary: {n_allowed} allowed  {n_modified} modified  {n_blocked} blocked")
    print()


def stats_main() -> None:
    """Entry point for 'partenit-stats' command."""
    parser = argparse.ArgumentParser(
        prog="partenit-stats",
        description="Show a statistical summary of Partenit guard decisions",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="./decisions/",
        help="Path to decisions directory or .jsonl/.json file (default: ./decisions/)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format: text (default) or json (machine-readable)",
    )
    args = parser.parse_args()
    sys.exit(_cmd_stats(args))


# ---------------------------------------------------------------------------
# partenit-log export
# ---------------------------------------------------------------------------


def _load_packets_from(path: str) -> list:
    """Load DecisionPackets from path (json / jsonl / directory)."""
    from partenit.core.models import DecisionPacket
    from partenit.decision_log.storage import LocalFileStorage

    p = Path(path)
    packets: list = []

    if p.is_file():
        if p.suffix == ".jsonl":
            import jsonlines  # type: ignore[import]

            with jsonlines.open(p) as reader:
                for obj in reader:
                    packets.append(DecisionPacket.model_validate(obj))
        elif p.suffix == ".json":
            import json

            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                packets = [DecisionPacket.model_validate(d) for d in data]
            else:
                packets = [DecisionPacket.model_validate(data)]
    elif p.is_dir():
        storage = LocalFileStorage(str(p))
        packets = list(storage.read_all())
        if not packets:
            # recurse into session subdirectories
            for sub in sorted(p.iterdir()):
                if sub.is_dir():
                    st = LocalFileStorage(str(sub))
                    packets.extend(list(st.read_all()))
    return packets


def _cmd_export(args: argparse.Namespace) -> int:
    """Export decision packets to JSON or CSV."""
    import json

    # If --session is specified, resolve to path/session_name/
    load_path = args.path
    session_filter = getattr(args, "session", None)
    if session_filter:
        candidate = Path(args.path) / session_filter
        if candidate.is_dir():
            load_path = str(candidate)
        else:
            print(f"ERROR: session '{session_filter}' not found under {args.path}", file=sys.stderr)
            return 1

    packets = _load_packets_from(load_path)
    if not packets:
        print(f"No packets found at: {args.path}", file=sys.stderr)
        return 1

    fmt = (args.format or "json").lower()
    out_path = Path(args.output) if args.output else None

    if fmt == "json":
        data = [json.loads(p.model_dump_json()) for p in packets]
        text = json.dumps(data, indent=2, ensure_ascii=False)
        if out_path:
            out_path.write_text(text, encoding="utf-8")
            print(f"Exported {len(packets)} packets → {out_path}")
        else:
            print(text)

    elif fmt == "jsonl":
        lines = [p.model_dump_json() for p in packets]
        text = "\n".join(lines) + "\n"
        if out_path:
            out_path.write_text(text, encoding="utf-8")
            print(f"Exported {len(packets)} packets → {out_path}")
        else:
            print(text, end="")

    elif fmt == "csv":
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "packet_id",
                "timestamp",
                "action_requested",
                "allowed",
                "modified",
                "risk_score",
                "applied_policies",
                "rejection_reason",
                "fingerprint",
            ]
        )
        for p in packets:
            gd = p.guard_decision
            modified = gd.modified_params is not None and bool(gd.modified_params)
            writer.writerow(
                [
                    p.packet_id,
                    p.timestamp.isoformat(),
                    p.action_requested,
                    gd.allowed,
                    modified,
                    f"{gd.risk_score.value:.4f}" if gd.risk_score else "",
                    ";".join(gd.applied_policies),
                    gd.rejection_reason or "",
                    p.fingerprint,
                ]
            )
        text = buf.getvalue()
        if out_path:
            out_path.write_text(text, encoding="utf-8")
            print(f"Exported {len(packets)} packets → {out_path}")
        else:
            print(text, end="")

    else:
        print(f"Unknown format: {fmt!r}. Choose: json, jsonl, csv", file=sys.stderr)
        return 1

    return 0


def export_main() -> None:
    """Entry point for 'partenit-export' command."""
    parser = argparse.ArgumentParser(
        prog="partenit-export",
        description="Export Partenit decision packets to JSON, JSONL, or CSV",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="./decisions/",
        help="Path to decisions directory or file (default: ./decisions/)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["json", "jsonl", "csv"],
        default="json",
        help="Output format: json (default), jsonl, csv",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--session",
        "-s",
        default=None,
        metavar="NAME",
        help="Export only a specific session subdirectory",
    )
    args = parser.parse_args()
    sys.exit(_cmd_export(args))


if __name__ == "__main__":
    main()
