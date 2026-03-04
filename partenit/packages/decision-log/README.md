[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

## partenit-decision-log

**Purpose:** reference implementation for creating, storing, and verifying `DecisionPacket` objects.

Responsibilities:
- Provide a `DecisionLogger` that:
  - builds `DecisionPacket` instances from inputs (mission, plan, risk, policies, observations)
  - computes and verifies SHA256-based fingerprints
  - persists packets via pluggable storage backends
- Offer a simple local storage backend (JSONL files).
- Expose utilities to query and analyze logs:
  - `DecisionArchive`
  - audit report and CSV exporters
- Ship a CLI (`partenit-log`) for verification and reporting.

Schema-level contracts are defined in `partenit-core` and exported into `schemas/`.

[<img src="../../../partenit_robot.png" alt="Partenit robot" width="320" />](https://partenit.io)

Made with love for the future at [Partenit](https://partenit.io).

