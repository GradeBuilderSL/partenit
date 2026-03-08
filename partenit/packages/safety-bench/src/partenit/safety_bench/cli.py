"""
partenit-bench CLI

Commands:
    partenit-bench run ./scenarios/human_crossing.yaml
    partenit-bench run ./scenarios/human_crossing.yaml --with-guard --without-guard --report report.html
    partenit-bench run-all ./scenarios/ --with-guard --without-guard
    partenit-bench report ./scenarios/ --output report.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cmd_run(args: argparse.Namespace) -> int:
    from partenit.safety_bench.scenario import ScenarioRunner

    try:
        from rich.console import Console

        console = Console()
    except ImportError:
        console = None

    seed = args.seed
    runner = ScenarioRunner()
    config = runner.load(args.path)

    modes = []
    if args.with_guard and args.without_guard:
        modes = [True, False]
    elif args.without_guard:
        modes = [False]
    elif args.compare:
        modes = [True, False]
    else:
        modes = [True]  # default: with guard

    results = []
    failures = 0
    for with_guard in modes:
        result = runner.run(config, with_guard=with_guard, seed=seed)
        results.append(result)
        if console:
            console.print(result.summary())
        else:
            print(result.summary())
        if result.expected_events_missed:
            failures += 1

    if args.report:
        from partenit.safety_bench.benchmarks.report_html import generate_html_report

        html = generate_html_report(results, title=f"Partenit Bench — {config.scenario_id}")
        Path(args.report).write_text(html, encoding="utf-8")
        print(f"HTML report written to {args.report}")

    return 0 if failures == 0 else 1


def _cmd_run_all(args: argparse.Namespace) -> int:
    from partenit.safety_bench.scenario import ScenarioRunner

    seed = args.seed
    directory = Path(args.path)
    files = list(directory.glob("**/*.yaml")) + list(directory.glob("**/*.yml"))

    if not files:
        print(f"No scenario files found in {directory}", file=sys.stderr)
        return 1

    runner = ScenarioRunner()
    failures = 0
    all_results = []

    for path in sorted(files):
        try:
            config = runner.load(path)
            result = runner.run(config, with_guard=True, seed=seed)
            all_results.append(result)
            status = "PASS" if not result.expected_events_missed else "FAIL"
            print(f"{status}: {path.name} — {result.summary().splitlines()[1].strip()}")
            if result.expected_events_missed:
                failures += 1

            if args.without_guard:
                result_ng = runner.run(config, with_guard=False, seed=seed)
                all_results.append(result_ng)
        except Exception as e:
            print(f"ERROR: {path.name} — {e}", file=sys.stderr)
            failures += 1

    if args.report and all_results:
        from partenit.safety_bench.benchmarks.report_html import generate_html_report

        html = generate_html_report(all_results, title="Partenit Safety Bench — All Scenarios")
        Path(args.report).write_text(html, encoding="utf-8")
        print(f"HTML report written to {args.report}")

    print(f"\n{len(files) - failures}/{len(files)} scenarios passed")
    return 0 if failures == 0 else 1


def _cmd_report(args: argparse.Namespace) -> int:
    from partenit.safety_bench.benchmarks.report_html import generate_html_report
    from partenit.safety_bench.scenario import ScenarioRunner

    seed = args.seed
    directory = Path(args.path) if args.path else Path("./scenarios/")
    files = list(directory.glob("**/*.yaml"))

    if not files:
        print("No scenario files found", file=sys.stderr)
        return 1

    runner = ScenarioRunner()
    all_results = []

    for path in sorted(files):
        try:
            config = runner.load(path)
            with_guard = runner.run(config, with_guard=True, seed=seed)
            without_guard = runner.run(config, with_guard=False, seed=seed)
            all_results.extend([with_guard, without_guard])
        except Exception as e:
            print(f"WARN: {path.name} — {e}", file=sys.stderr)

    if not all_results:
        print("No results generated", file=sys.stderr)
        return 1

    html = generate_html_report(all_results, title="Partenit Safety Bench Report")

    if args.output:
        Path(args.output).write_text(html, encoding="utf-8")
        print(f"HTML report written to {args.output}")
    else:
        print(html)

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="partenit-bench",
        description="Partenit Safety Bench CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Run a single scenario")
    p_run.add_argument("path", help="Path to scenario YAML file")
    p_run.add_argument(
        "--with-guard", action="store_true", default=True, help="Run with guard (default)"
    )
    p_run.add_argument("--without-guard", action="store_true", help="Run without guard")
    p_run.add_argument("--compare", action="store_true", help="Run both with and without guard")
    p_run.add_argument("--report", metavar="FILE", help="Write HTML report to FILE")
    p_run.add_argument(
        "--seed", type=int, default=42, help="Random seed for determinism (default: 42)"
    )

    # run-all
    p_all = sub.add_parser("run-all", help="Run all scenarios in a directory")
    p_all.add_argument("path", help="Path to scenarios directory")
    p_all.add_argument("--with-guard", action="store_true", default=True)
    p_all.add_argument("--without-guard", action="store_true", help="Also run without guard")
    p_all.add_argument("--report", metavar="FILE", help="Write HTML report to FILE")
    p_all.add_argument(
        "--seed", type=int, default=42, help="Random seed for determinism (default: 42)"
    )

    # report
    p_report = sub.add_parser(
        "report", help="Generate HTML bench report from a scenarios directory"
    )
    p_report.add_argument("path", nargs="?", help="Scenarios directory (default: ./scenarios/)")
    p_report.add_argument(
        "--output", "-o", metavar="FILE", help="Output HTML file (default: stdout)"
    )
    p_report.add_argument(
        "--seed", type=int, default=42, help="Random seed for determinism (default: 42)"
    )

    args = parser.parse_args()
    handlers = {
        "run": _cmd_run,
        "run-all": _cmd_run_all,
        "report": _cmd_report,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
