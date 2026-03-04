[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

## partenit-core

**Purpose:** shared types, contracts, and base classes used across the Partenit ecosystem.

This package defines the core data models such as:
- `StructuredObservation`
- `PolicyRule`
- `RiskScore`
- `DecisionPacket`
- `DecisionFingerprint`
- `TrustState`
- `SafetyEvent`

All other packages **must** import these contracts from `partenit-core` rather than redefining them.

Planned modules (no implementation yet):
- `models.py` — Pydantic v2 models for all core types
- `schema_export.py` — utilities to export JSON Schemas into the top-level `schemas/` directory

Installation and usage examples will be added once the initial implementation is complete.

[<img src="../../../partenit_robot.png" alt="Partenit robot" width="320" />](https://partenit.io)

Made with love for the future at [Partenit](https://partenit.io).

