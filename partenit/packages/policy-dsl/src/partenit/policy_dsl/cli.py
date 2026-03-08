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

    args = parser.parse_args()

    handlers = {
        "validate": _cmd_validate,
        "bundle": _cmd_bundle,
        "check-conflicts": _cmd_check_conflicts,
        "sim": _cmd_sim,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
