[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

## partenit-policy-dsl

**Purpose:** human-readable YAML policy language for defining safety rules that can be executed by the Partenit guard and engines.

This package will provide:
- A YAML schema for safety policies (conditions, actions, releases, priorities).
- Parsers that load `.yaml` files into `PolicyRule` objects from `partenit-core`.
- Validation and conflict detection for policy bundles.
- A CLI to validate, bundle, and inspect policy sets.

Planned components:
- `parser.py` — YAML → internal models
- `validator.py` — schema and consistency checks
- `bundle.py` — `PolicyBundle` type with versioning and hashing
- `conflicts.py` — conflict detection by priority and condition overlap
- `cli.py` — `partenit-policy` command-line interface

Detailed format examples will live in `docs/guides/writing-policies.md`.

[<img src="../../../partenit_robot.png" alt="Partenit robot" width="320" />](https://partenit.io)

Made with love for the future at [Partenit](https://partenit.io).

