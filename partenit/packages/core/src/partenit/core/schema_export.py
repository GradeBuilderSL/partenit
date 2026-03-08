"""
Schema export utility for partenit-core.

Generates JSON Schema files from Pydantic v2 models.

Usage:
    partenit-schema export --output ./schemas/
    python -m partenit.core.schema_export
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from partenit.core.models import DecisionFingerprint, DecisionPacket

_SCHEMAS: list[tuple[str, type]] = [
    ("DecisionPacket.schema.json", DecisionPacket),
    ("DecisionFingerprint.schema.json", DecisionFingerprint),
]


def export_schemas(output_dir: Path) -> None:
    """Export all public JSON Schemas to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in _SCHEMAS:
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["title"] = model.__name__
        path = output_dir / filename
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        print(f"Exported: {path}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="partenit-schema",
        description="Export Partenit JSON Schemas from Pydantic models",
    )
    sub = parser.add_subparsers(dest="command")

    exp = sub.add_parser("export", help="Export schemas to a directory")
    exp.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("schemas"),
        help="Output directory (default: ./schemas/)",
    )

    args = parser.parse_args()

    if args.command == "export":
        export_schemas(args.output)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
