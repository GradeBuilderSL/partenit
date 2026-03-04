"""
partenit-policy CLI

Commands:
    partenit-policy validate ./policies/
    partenit-policy bundle ./policies/ --output bundle.json
    partenit-policy check-conflicts ./policies/
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

    args = parser.parse_args()

    handlers = {
        "validate": _cmd_validate,
        "bundle": _cmd_bundle,
        "check-conflicts": _cmd_check_conflicts,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
