"""
partenit-policy CLI

Commands:
    partenit-policy validate ./policies/
    partenit-policy bundle ./policies/ --output bundle.json
    partenit-policy check-conflicts ./policies/
    partenit-policy sim --action navigate_to --speed 2.0 --human-distance 1.2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cmd_validate(args: argparse.Namespace) -> int:
    from partenit.policy_dsl.validator import PolicyValidator, ValidationError

    validator = PolicyValidator()
    path = Path(args.path)
    try:
        if path.is_dir():
            warnings = validator.validate_dir(path)
        else:
            warnings = validator.validate_file(path)
        for w in warnings:
            print(f"WARN: {w}")
        print(f"OK: validation passed ({len(warnings)} warnings)")
        return 0
    except ValidationError as e:
        for err in e.errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1


def _cmd_bundle(args: argparse.Namespace) -> int:
    from partenit.policy_dsl.bundle import PolicyBundleBuilder
    from partenit.policy_dsl.validator import ValidationError

    builder = PolicyBundleBuilder()
    path = Path(args.path)
    output = Path(args.output)
    try:
        if path.is_dir():
            bundle = builder.from_dir(path, version=args.version)
        else:
            bundle = builder.from_file(path, version=args.version)
        builder.export(bundle, output)
        print(f"Bundle: {len(bundle.rules)} rules → {output}")
        print(f"Hash:   {bundle.bundle_hash}")
        return 0
    except ValidationError as e:
        for err in e.errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1


def _cmd_check_conflicts(args: argparse.Namespace) -> int:
    from partenit.policy_dsl.conflicts import ConflictDetector
    from partenit.policy_dsl.parser import PolicyParser

    parser = PolicyParser()
    path = Path(args.path)
    if path.is_dir():
        rules = parser.load_dir(path)
    else:
        rules = parser.load_file(path)

    detector = ConflictDetector()
    conflicts = detector.detect(rules)

    if not conflicts:
        print(f"OK: no conflicts found in {len(rules)} rules")
        return 0

    print(f"Found {len(conflicts)} conflict(s):\n")
    for c in conflicts:
        print(c.describe())
        print()
    return 1 if args.fail_on_conflict else 0


def _cmd_sim(args: argparse.Namespace) -> int:
    """
    Simulate policy evaluation for given inputs.

    Shows which rules fire and what the effective output parameters are.
    """
    from partenit.policy_dsl.evaluator import PolicyEvaluator
    from partenit.policy_dsl.parser import PolicyParser

    # Build context from CLI args
    context: dict = {}
    if args.human_distance is not None:
        context["human"] = {"distance": args.human_distance}
    if args.human_confidence is not None:
        context.setdefault("human", {})["confidence"] = args.human_confidence
    if args.sensor_trust is not None:
        context["sensor_trust"] = args.sensor_trust
    if args.speed is not None:
        context["speed"] = args.speed

    # Load policies
    rules = []
    policy_path = args.policy_path or "."
    path = Path(policy_path)
    parser_obj = PolicyParser()
    try:
        if path.is_dir():
            rules = parser_obj.load_dir(path)
        elif path.exists():
            rules = parser_obj.load_file(path)
    except Exception as exc:
        print(f"ERROR loading policies from {policy_path}: {exc}", file=sys.stderr)
        return 1

    evaluator = PolicyEvaluator()
    result = evaluator.evaluate(rules, context)

    _print_sim_result(args.action, args.speed, context, result, rules)
    return 0


def _print_sim_result(action: str, speed, context: dict, result, all_rules) -> None:
    """Print policy simulation result."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()

        console.print("\n[bold cyan]Policy Simulator[/]\n")
        console.print("[bold]Input:[/]")
        console.print(f"  action:          {action}")
        if speed is not None:
            console.print(f"  speed:           {speed} m/s")
        if "human" in context:
            h = context["human"]
            if "distance" in h:
                console.print(f"  human.distance:  {h['distance']} m")
            if "confidence" in h:
                console.print(f"  human.confidence:{h['confidence']}")
        if "sensor_trust" in context:
            console.print(f"  sensor_trust:    {context['sensor_trust']}")
        console.print(f"  policies loaded: {len(all_rules)}\n")

        table = Table(show_header=True, header_style="bold")
        table.add_column("Rule", style="dim", width=32)
        table.add_column("Priority", width=16)
        table.add_column("Status", width=10)
        table.add_column("Effect")

        fired_ids = {r.rule_id for r in result.fired_rules}
        for rule in sorted(all_rules, key=lambda r: r.rule_id):
            fired = rule.rule_id in fired_ids
            status = "[green]FIRED[/]" if fired else "[dim]—[/]"
            effect = ""
            if fired:
                a = rule.action
                if a.type == "block":
                    effect = "[red]BLOCK[/]"
                elif a.type == "clamp":
                    effect = f"clamp {a.parameter} → {a.value}"
                else:
                    effect = str(a.type)
            table.add_row(rule.name or rule.rule_id, rule.priority, status, effect)

        console.print(table)

        clamps = result.get_clamps()
        console.print("\n[bold]Result:[/]")
        if result.has_violations:
            console.print("  Status:  [red]BLOCKED[/]")
        elif clamps:
            console.print("  Status:  [yellow]ALLOWED (modified)[/]")
            for param, val in clamps.items():
                console.print(f"  {param}: → {val}")
        else:
            console.print("  Status:  [green]ALLOWED[/]")
        console.print()

    except ImportError:
        # Plain fallback
        print("\nPolicy Simulator")
        print(f"Input: action={action}, context={context}, policies={len(all_rules)}")
        fired_ids = {r.rule_id for r in result.fired_rules}
        print("\nRules:")
        for rule in all_rules:
            fired = rule.rule_id in fired_ids
            mark = "FIRED" if fired else "    -"
            print(f"  [{mark}] {rule.name or rule.rule_id} [{rule.priority}]")
        clamps = result.get_clamps()
        print(
            "\nResult:",
            "BLOCKED" if result.has_violations else ("MODIFIED" if clamps else "ALLOWED"),
        )
        for p, v in clamps.items():
            print(f"  {p} → {v}")
        print()


def _cmd_diff(args: argparse.Namespace) -> int:
    """
    Compare two policy configurations.

    Shows added, removed, and changed rules.
    With --scenario: also runs the scenario with both configs and compares outcomes.
    """
    from partenit.policy_dsl.parser import PolicyParser

    parser_obj = PolicyParser()

    def _load(path_str: str) -> list:
        p = Path(path_str)
        if not p.exists():
            print(f"ERROR: path does not exist: {p}", file=sys.stderr)
            sys.exit(1)
        if p.is_dir():
            return parser_obj.load_dir(p)
        return parser_obj.load_file(p)

    rules_a = _load(args.policy_a)
    rules_b = _load(args.policy_b)

    # Build lookup dicts by rule_id
    by_id_a = {r.rule_id: r for r in rules_a}
    by_id_b = {r.rule_id: r for r in rules_b}

    added = [r for r in rules_b if r.rule_id not in by_id_a]
    removed = [r for r in rules_a if r.rule_id not in by_id_b]
    changed = []
    unchanged = []
    for rule_id, r_a in by_id_a.items():
        if rule_id in by_id_b:
            r_b = by_id_b[rule_id]
            if r_a.model_dump() != r_b.model_dump():
                changed.append((r_a, r_b))
            else:
                unchanged.append(r_a)

    # Run scenario comparison if requested
    scenario_results = None
    if args.scenario:
        scenario_results = _run_scenario_diff(args.policy_a, args.policy_b, args.scenario)

    _print_diff(
        args.policy_a,
        args.policy_b,
        added,
        removed,
        changed,
        unchanged,
        scenario_results,
    )
    return 0


def _run_scenario_diff(policy_a: str, policy_b: str, scenario_path: str) -> dict | None:
    """Run a scenario with both policy configs and return comparison dict."""
    try:
        from partenit.safety_bench.eval.runner import ControllerConfig, EvalRunner
    except ImportError:
        return None

    runner = EvalRunner()
    report = runner.run_scenario(
        Path(scenario_path),
        controllers=[
            ControllerConfig("v1", policy_paths=[policy_a]),
            ControllerConfig("v2", policy_paths=[policy_b]),
        ],
        seed=42,
    )

    m_a = report.get(Path(scenario_path).stem, "v1")
    m_b = report.get(Path(scenario_path).stem, "v2")
    if not m_a or not m_b:
        return None

    return {
        "scenario": Path(scenario_path).stem,
        "v1": m_a,
        "v2": m_b,
    }


def _print_diff(
    path_a: str,
    path_b: str,
    added: list,
    removed: list,
    changed: list,
    unchanged: list,
    scenario_results: dict | None,
) -> None:
    """Print policy diff result."""
    try:
        import rich  # noqa: F401

        _rich_diff(path_a, path_b, added, removed, changed, unchanged, scenario_results)
    except ImportError:
        _plain_diff(path_a, path_b, added, removed, changed, unchanged, scenario_results)


def _rich_diff(path_a, path_b, added, removed, changed, unchanged, scenario_results) -> None:
    from rich.console import Console
    from rich.rule import Rule
    from rich.table import Table

    console = Console()
    console.print()
    console.print(Rule(f"[bold]Policy Diff[/]  {Path(path_a).name} → {Path(path_b).name}"))
    console.print()

    # Rule changes
    total_a = len(added) + len(removed) + len(changed) + len(unchanged)
    total_b = total_a - len(removed) + len(added)
    console.print(
        f"[dim]Rules: {total_a} → {total_b}"
        f"  ([green]+{len(added)}[/] added  "
        f"[red]-{len(removed)}[/] removed  "
        f"[yellow]~{len(changed)}[/] changed  "
        f"[dim]{len(unchanged)} unchanged)[/]"
    )
    console.print()

    if added:
        console.print("[bold green]Added rules:[/]")
        for r in added:
            console.print(
                f"  [green]+[/] [bold]{r.rule_id}[/]  [dim]{r.priority}[/]  {r.name or ''}"
            )
        console.print()

    if removed:
        console.print("[bold red]Removed rules:[/]")
        for r in removed:
            console.print(f"  [red]-[/] [bold]{r.rule_id}[/]  [dim]{r.priority}[/]  {r.name or ''}")
        console.print()

    if changed:
        console.print("[bold yellow]Changed rules:[/]")
        for r_a, r_b in changed:
            console.print(f"  [yellow]~[/] [bold]{r_a.rule_id}[/]")
            if r_a.priority != r_b.priority:
                console.print(f"      priority: [red]{r_a.priority}[/] → [green]{r_b.priority}[/]")
            if r_a.action.value != r_b.action.value and r_b.action.value is not None:
                console.print(
                    f"      action.value: [red]{r_a.action.value}[/] → [green]{r_b.action.value}[/]"
                )
            if r_a.enabled != r_b.enabled:
                console.print(f"      enabled: [red]{r_a.enabled}[/] → [green]{r_b.enabled}[/]")
        console.print()

    if not added and not removed and not changed:
        console.print("[green]No rule changes.[/]\n")

    # Scenario comparison
    if scenario_results:
        sr = scenario_results
        m_a = sr["v1"]
        m_b = sr["v2"]

        console.print(Rule(f"[bold]Scenario impact[/]  {sr['scenario']}"))
        console.print()

        table = Table(show_header=True, header_style="bold", border_style="dim")
        table.add_column("Metric", style="dim", width=28)
        table.add_column(f"v1  ({Path(path_a).name})", width=14, justify="right")
        table.add_column(f"v2  ({Path(path_b).name})", width=14, justify="right")
        table.add_column("Change", width=14)

        def _delta(a, b, lower_is_better=True, fmt=".2f"):
            if a is None or b is None:
                return "—"
            diff = b - a
            if abs(diff) < 0.001:
                return "[dim]=[/]"
            better = (diff < 0) == lower_is_better
            color = "green" if better else "red"
            sign = "↓" if diff < 0 else "↑"
            return f"[{color}]{sign} {abs(diff):{fmt}}[/]"

        def _pct(val):
            return f"{val * 100:.0f}%" if val is not None else "—"

        def _fval(val, fmt=".2f"):
            return f"{val:{fmt}}" if val is not None else "—"

        table.add_row(
            "Safety grade",
            m_a.grade,
            m_b.grade,
            "[green]improved[/]"
            if (m_b.overall_score or 0) > (m_a.overall_score or 0)
            else "[red]worse[/]"
            if (m_b.overall_score or 0) < (m_a.overall_score or 0)
            else "[dim]same[/]",
        )
        table.add_row(
            "Overall score",
            _fval(m_a.overall_score),
            _fval(m_b.overall_score),
            _delta(m_a.overall_score, m_b.overall_score, lower_is_better=False),
        )
        table.add_row(
            "Collision rate",
            _pct(m_a.collision_rate),
            _pct(m_b.collision_rate),
            _delta(m_a.collision_rate, m_b.collision_rate, lower_is_better=True, fmt=".1%"),
        )
        table.add_row(
            "Unsafe accept rate",
            _pct(m_a.unsafe_acceptance_rate),
            _pct(m_b.unsafe_acceptance_rate),
            _delta(
                m_a.unsafe_acceptance_rate,
                m_b.unsafe_acceptance_rate,
                lower_is_better=True,
                fmt=".1%",
            ),
        )
        table.add_row(
            "Task completion",
            _pct(m_a.task_completion_rate),
            _pct(m_b.task_completion_rate),
            _delta(
                m_a.task_completion_rate,
                m_b.task_completion_rate,
                lower_is_better=False,
                fmt=".1%",
            ),
        )
        if m_a.min_human_distance_m is not None:
            table.add_row(
                "Min human distance",
                f"{m_a.min_human_distance_m:.2f} m",
                f"{m_b.min_human_distance_m:.2f} m" if m_b.min_human_distance_m else "—",
                _delta(
                    m_a.min_human_distance_m,
                    m_b.min_human_distance_m,
                    lower_is_better=False,
                ),
            )

        console.print(table)
        console.print()
    elif getattr(_cmd_diff, "_scenario_requested", False):
        console.print("[dim]Scenario comparison unavailable: install partenit-safety-bench[/]\n")


def _plain_diff(path_a, path_b, added, removed, changed, unchanged, scenario_results) -> None:
    print(f"\nPolicy Diff: {Path(path_a).name} → {Path(path_b).name}")
    print("─" * 58)
    total_a = len(added) + len(removed) + len(changed) + len(unchanged)
    total_b = total_a - len(removed) + len(added)
    print(
        f"Rules: {total_a} → {total_b}  (+{len(added)} added  -{len(removed)} removed  ~{len(changed)} changed)"
    )
    print()

    for r in added:
        print(f"  + {r.rule_id}  [{r.priority}]  {r.name or ''}")
    for r in removed:
        print(f"  - {r.rule_id}  [{r.priority}]  {r.name or ''}")
    for r_a, r_b in changed:
        print(f"  ~ {r_a.rule_id}")
        if r_a.priority != r_b.priority:
            print(f"      priority: {r_a.priority} → {r_b.priority}")
        if r_a.action.value != r_b.action.value:
            print(f"      action.value: {r_a.action.value} → {r_b.action.value}")

    if not added and not removed and not changed:
        print("  No rule changes.")

    if scenario_results:
        sr = scenario_results
        m_a, m_b = sr["v1"], sr["v2"]
        print(f"\nScenario impact: {sr['scenario']}")
        print(f"  {'':28} v1         v2")
        print(f"  {'─' * 50}")
        print(f"  {'Safety grade':<28} {m_a.grade:<10} {m_b.grade}")
        print(
            f"  {'Overall score':<28} {m_a.overall_score or 0:.2f}      {m_b.overall_score or 0:.2f}"
        )
        if m_a.min_human_distance_m is not None:
            print(
                f"  {'Min human distance':<28} {m_a.min_human_distance_m:.2f} m    "
                f"{m_b.min_human_distance_m:.2f} m"
                if m_b.min_human_distance_m
                else ""
            )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="partenit-policy",
        description="Partenit Policy DSL CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # validate
    p_validate = sub.add_parser("validate", help="Validate policy YAML file or directory")
    p_validate.add_argument("path", help="Path to YAML file or directory")

    # bundle
    p_bundle = sub.add_parser("bundle", help="Bundle policies into a JSON file")
    p_bundle.add_argument("path", help="Path to YAML file or directory")
    p_bundle.add_argument("--output", "-o", default="bundle.json", help="Output JSON path")
    p_bundle.add_argument("--version", "-v", default="0.1.0", help="Bundle version string")

    # check-conflicts
    p_conflicts = sub.add_parser("check-conflicts", help="Detect conflicting rules")
    p_conflicts.add_argument("path", help="Path to YAML file or directory")
    p_conflicts.add_argument(
        "--fail-on-conflict",
        action="store_true",
        default=True,
        help="Exit with code 1 if conflicts are found (default: True)",
    )

    # sim
    p_sim = sub.add_parser("sim", help="Simulate policy evaluation for given inputs")
    p_sim.add_argument("--action", default="navigate_to", help="Action name (default: navigate_to)")
    p_sim.add_argument("--speed", type=float, default=None, help="Requested speed (m/s)")
    p_sim.add_argument("--human-distance", type=float, default=None, help="Human distance (m)")
    p_sim.add_argument(
        "--human-confidence", type=float, default=None, help="Human detection confidence (0-1)"
    )
    p_sim.add_argument("--sensor-trust", type=float, default=None, help="Global sensor trust (0-1)")
    p_sim.add_argument("--policy-path", default=None, help="Path to policies (file or dir)")

    # diff
    p_diff = sub.add_parser(
        "diff",
        help="Compare two policy configurations (show added/removed/changed rules)",
    )
    p_diff.add_argument("policy_a", help="First policy file or directory (baseline)")
    p_diff.add_argument("policy_b", help="Second policy file or directory (new version)")
    p_diff.add_argument(
        "--scenario",
        metavar="SCENARIO",
        default=None,
        help="Optional: scenario YAML to compare outcomes (requires partenit-safety-bench)",
    )

    args = parser.parse_args()

    handlers = {
        "validate": _cmd_validate,
        "bundle": _cmd_bundle,
        "check-conflicts": _cmd_check_conflicts,
        "sim": _cmd_sim,
        "diff": _cmd_diff,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
