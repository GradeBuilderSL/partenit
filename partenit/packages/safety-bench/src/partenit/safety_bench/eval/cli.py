"""
partenit-eval CLI

Commands:
    partenit-eval run scenario.yaml [--report eval.html]
    partenit-eval run scenario.yaml --compare policies/baseline.yaml policies/v2.yaml
    partenit-eval run-suite scenarios/ --report eval.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cmd_run(args: argparse.Namespace) -> int:
    from partenit.safety_bench.eval.runner import ControllerConfig, EvalRunner
    from partenit.safety_bench.eval.report_eval import generate_eval_html

    controllers: list[ControllerConfig] = []

    if args.compare:
        # Each --compare value is a policy file/dir
        for i, p in enumerate(args.compare):
            label = Path(p).stem if p else f"controller_{i}"
            controllers.append(ControllerConfig(name=label, policy_paths=[p]))
        # Also add baseline (no guard)
        controllers.insert(0, ControllerConfig(name="baseline", policy_paths=[]))
    else:
        # Default: baseline vs guarded (using scenario's own policies)
        controllers = [
            ControllerConfig("baseline", policy_paths=[]),
            ControllerConfig("guarded", policy_paths=[]),  # will use scenario policies
        ]
        # For guarded: use scenario's own policies (ScenarioRunner will load them)
        # We signal this by passing with_guard=True which is the default

    runner = EvalRunner()
    try:
        report = runner.run_scenario(
            args.scenario,
            controllers=controllers,
            seed=args.seed,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(report.summary_table())

    if args.report:
        html = generate_eval_html(report, title=f"Eval — {Path(args.scenario).stem}")
        Path(args.report).write_text(html, encoding="utf-8")
        print(f"\nReport written to {args.report}")

    return 0


def _cmd_run_suite(args: argparse.Namespace) -> int:
    from partenit.safety_bench.eval.runner import ControllerConfig, EvalRunner
    from partenit.safety_bench.eval.report_eval import generate_eval_html

    controllers = [
        ControllerConfig("baseline", policy_paths=[]),
        ControllerConfig("guarded", policy_paths=[]),
    ]

    runner = EvalRunner()
    try:
        report = runner.run_suite(
            args.directory,
            controllers=controllers,
            seed=args.seed,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not report.metrics:
        print("No scenarios found or all failed.")
        return 1

    print(report.summary_table())

    if args.report:
        html = generate_eval_html(report, title=f"Eval Suite — {args.directory}")
        Path(args.report).write_text(html, encoding="utf-8")
        print(f"\nReport written to {args.report}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="partenit-eval",
        description="Partenit Robot Evaluation Platform — measure safety grade A–F",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Evaluate controllers on a single scenario")
    p_run.add_argument("scenario", help="Path to scenario YAML file")
    p_run.add_argument(
        "--compare",
        nargs="+",
        metavar="POLICY_PATH",
        help="Compare specific policy sets (each becomes a controller)",
    )
    p_run.add_argument("--report", "-o", help="Output HTML report path")
    p_run.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")

    # run-suite
    p_suite = sub.add_parser("run-suite", help="Evaluate controllers on all scenarios in a directory")
    p_suite.add_argument("directory", help="Directory containing scenario YAML files")
    p_suite.add_argument("--report", "-o", help="Output HTML report path")
    p_suite.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")

    args = parser.parse_args()
    handlers = {
        "run": _cmd_run,
        "run-suite": _cmd_run_suite,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
