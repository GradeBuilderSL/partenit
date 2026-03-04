[<img src="../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# DecisionPacket Reference

`DecisionPacket` is the **Partenit open standard** for auditing a single guard decision cycle.
Every guard evaluation produces exactly one `DecisionPacket`, whether the action was allowed,
modified, or blocked.

The authoritative JSON Schema lives at `schemas/DecisionPacket.schema.json`.
The Pydantic v2 source of truth is `partenit.core.models.DecisionPacket`.

No breaking changes to this format are allowed without a major version bump.

---

## Why DecisionPacket Exists

Every decision made by `AgentGuard` must be:

- **Reproducible** — given the same inputs, the same decision must be reachable.
- **Explainable** — which policies fired, what risk score was computed, and why.
- **Auditable** — a cryptographic fingerprint proves the record has not been tampered with.

`DecisionPacket` captures all of this in one document.

---

## Full Field Reference

| Field | Type | Description |
|---|---|---|
| `packet_id` | `str` (UUID) | Unique identifier generated at creation time |
| `timestamp` | `datetime` | UTC time of packet creation |
| `mission_goal` | `str` | Optional human-readable goal for this mission |
| `action_requested` | `str` | The action the robot/LLM attempted (e.g. `"navigate_to"`) |
| `action_params` | `dict` | Parameters passed to the action |
| `guard_decision` | `GuardDecision` | Full guard outcome (see below) |
| `observation_hashes` | `list[str]` | SHA256 hashes of `StructuredObservation` inputs used |
| `world_state_hash` | `str \| None` | SHA256 of the world state snapshot at decision time |
| `policy_bundle_version` | `str \| None` | Version string of the loaded `PolicyBundle` |
| `model_versions` | `dict[str, str]` | Version tags of all packages (for audit reproducibility) |
| `latency_ms` | `dict[str, float]` | Latency breakdown: `{"policy_check": 2.1, "risk_score": 0.8, "total": 3.1}` |
| `conflicts_resolved` | `list[dict]` | List of policy conflicts that were resolved before this decision |
| `violations_checked` | `list[str]` | `rule_id` list of all rules that were evaluated |
| `fingerprint` | `str` | SHA256 fingerprint over the full packet content (see below) |

---

## GuardDecision Fields

`guard_decision` embeds the full `GuardDecision` model:

| Field | Type | Description |
|---|---|---|
| `allowed` | `bool` | Whether the action is permitted to execute |
| `modified_params` | `dict \| None` | Rewritten parameters if guard clamped values (e.g. speed reduced) |
| `rejection_reason` | `str \| None` | Human-readable explanation when `allowed=False` |
| `risk_score` | `RiskScore` | Composite risk score with contributor breakdown |
| `applied_policies` | `list[str]` | `rule_id` list of all policies that fired |
| `suggested_alternative` | `dict \| None` | Guard-proposed safe alternative params |
| `timestamp` | `datetime` | UTC time of this guard evaluation |
| `latency_ms` | `float` | Wall-clock time for this guard check |

---

## Fingerprint Computation

The fingerprint is a SHA256 hash of the serialized packet content, computed by:

```python
import hashlib, json

def compute_fingerprint(packet: DecisionPacket) -> str:
    data = packet.model_dump(mode="json", exclude={"fingerprint"})
    content = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()
```

The fingerprint covers every field except `fingerprint` itself.
Any tampering with any field invalidates it.

---

## Creating and Verifying Packets

```python
from partenit.decision_log import DecisionLogger

log = DecisionLogger(storage_dir="./decisions/")

# Create (fingerprint computed automatically)
packet = log.create_packet(
    action_requested="navigate_to",
    action_params={"zone": "A3", "speed": 1.5},
    guard_decision=decision,
    model_versions={"trust_engine": "0.1.0", "policy_dsl": "0.1.0"},
    latency_ms={"policy_check": 2.1, "risk_score": 0.8, "total": 3.1},
)

# Verify integrity
assert log.verify_packet(packet)        # True — untampered
assert packet.compute_fingerprint() == packet.fingerprint   # identical

# Detached fingerprint (for separate storage)
fp = log.get_fingerprint(packet)
assert fp.verify(packet)               # True
```

---

## Storage Format (JSONL)

`LocalFileStorage` writes one JSON object per line to a `.jsonl` file:

```
./decisions/2025-01-01.jsonl
./decisions/2025-01-02.jsonl
...
```

Each line is a full `DecisionPacket` serialized with `model_dump(mode="json")`.

---

## CLI Tools

```bash
# Verify integrity of all packets in a directory
partenit-log verify ./decisions/

# Generate a markdown audit report
partenit-log report ./decisions/ --from 2025-01-01 --output report.md

# Inspect a single packet by ID
partenit-log inspect <packet_id>
```

---

## Invariants (Acceptance Criteria)

- `DecisionPacket` MUST be created on every guard decision, including safe stops.
- There is no code path in `partenit-decision-log` that skips logging.
- `partenit-log verify` MUST pass on all generated packets.
- Schema changes require a major version bump of `partenit-core`.

---

## JSON Schema

The machine-readable schema is generated from the Pydantic model:

```bash
partenit-schema export --output ./schemas/
```

This writes `schemas/DecisionPacket.schema.json` and `schemas/DecisionFingerprint.schema.json`.
