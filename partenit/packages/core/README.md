[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# partenit-core

> **The shared data contracts for the entire Partenit ecosystem.**

`partenit-core` defines every type used across all Partenit packages.
Nothing else in the stack redefines these types — they all import from here.

```bash
pip install partenit-core
```

---

## Why this exists

Every Partenit package — guard, adapter, trust engine, decision log —
speaks the same language. `partenit-core` is that language:
a set of Pydantic v2 models that are the open standard for
robot decision packets, safety policies, and sensor observations.

---

## Data models

### Observations

```python
from partenit.core.models import StructuredObservation

obs = StructuredObservation(
    object_id="human-01",
    class_name="human",
    distance_m=1.2,
    confidence=0.91,
    position={"x": 1.2, "y": 0.0, "z": 0.0},
)
# obs.treat_as_human → True  (auto-set when class_name == "human")
```

| Field | Description |
|---|---|
| `object_id` | Unique identifier for this object |
| `class_name` | Detected class: `"human"`, `"obstacle"`, etc. |
| `distance_m` | Distance in metres from robot |
| `confidence` | Detection confidence 0–1 |
| `position` | World coordinates dict |
| `velocity` | Velocity dict (optional) |
| `treat_as_human` | Force human-safe behaviour (auto-set if class is `"human"`) |
| `class_set` | Conformal prediction set — if `"human"` in set, treat_as_human=True |

---

### Policies

```python
from partenit.core.models import PolicyRule, PolicyBundle, PolicyPriority

rule = PolicyRule(
    rule_id="emergency_stop",
    name="Emergency Stop",
    priority=PolicyPriority.SAFETY_CRITICAL,
    provenance="ISO 3691-4 section 5.3",
    condition={"type": "threshold", "metric": "human.distance",
               "operator": "less_than", "value": 0.8},
    action={"type": "block"},
)
```

Priority hierarchy: `safety_critical > legal > task > efficiency`

---

### Risk and decisions

```python
from partenit.core.models import RiskScore, GuardDecision

risk = RiskScore(value=0.72, contributors={"human_distance": 0.85, "speed": 0.45})

decision = GuardDecision(
    allowed=True,
    modified_params={"speed": 0.3},   # guard clamped speed
    risk_score=risk,
    applied_policies=["human_proximity_slowdown"],
)
```

| Field | Description |
|---|---|
| `allowed` | Whether the action may execute |
| `modified_params` | Safe parameter overrides (speed clamped, zone changed, …) |
| `rejection_reason` | Policy rule that blocked the action |
| `risk_score` | 0–1 score with per-feature attribution |
| `applied_policies` | All rule IDs that fired |
| `suggested_alternative` | Alternative safe action (optional) |

---

### Trust

```python
from partenit.core.models import TrustState, TrustMode

trust = TrustState(
    sensor_id="depth_camera",
    trust_level=0.65,
    mode=TrustMode.DEGRADED,
    degradation_reasons=["frame_rate_drop", "depth_variance_spike"],
)
```

Modes: `NOMINAL (>0.8)` · `DEGRADED (0.5–0.8)` · `UNRELIABLE (0.2–0.5)` · `FAILED (<0.2)`

---

### Safety events

```python
from partenit.core.models import SafetyEvent, SafetyEventType

event = SafetyEvent(
    event_type=SafetyEventType.SLOWDOWN,
    trigger_rule="human_proximity_slowdown",
    risk_at_trigger=0.64,
)
```

Types: `STOP` · `SLOWDOWN` · `VIOLATION` · `NEAR_MISS` · `POLICY_CONFLICT`

---

### DecisionPacket — the audit record

Every action produces exactly one `DecisionPacket`, whether allowed, modified, or blocked.

```python
from partenit.core.models import DecisionPacket

# Created by DecisionLogger — do not construct manually
packet.packet_id          # UUID
packet.timestamp          # UTC datetime
packet.action_requested   # action name
packet.action_params      # original parameters
packet.guard_decision     # GuardDecision (above)
packet.applied_policies   # list of rule IDs
packet.observation_hashes # SHA-256 of sensor inputs
packet.fingerprint        # SHA-256 of entire packet (tamper detection)
```

JSON Schema: [`/schemas/DecisionPacket.schema.json`](../../../schemas/DecisionPacket.schema.json)

---

## Schema export

```python
from pathlib import Path
from partenit.core.schema_export import export_schemas

# Write DecisionPacket.schema.json and DecisionFingerprint.schema.json
export_schemas(Path("schemas/"))
```

Run `python -c "from partenit.core.schema_export import export_schemas; ..."` to regenerate
schemas after model changes. The CI schema-check job verifies they are up-to-date.

---

## Dependencies

```
pydantic >= 2.0
```

No other runtime dependencies. `partenit-core` is the foundation
that every other package builds on.

---

[Documentation](../../../docs/) · [Examples](../../../examples/) · [Issues](https://github.com/GradeBuilderSL/partenit/issues)
