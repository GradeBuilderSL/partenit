[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# partenit-decision-log

> **Every robot decision. Logged. Verified. Explainable.**

`partenit-decision-log` records every guard decision as a `DecisionPacket` — a structured
audit record with a SHA-256 fingerprint. You can replay, verify, and explain any decision
after the fact, whether the robot acted correctly or not.

```bash
pip install partenit-decision-log
```

---

## Why this exists

When a robot stops unexpectedly, you need to know **why** — not just that it stopped.
`partenit-decision-log` gives you:

- A full record of every decision: action requested, policies fired, risk score, params
- Cryptographic fingerprints to prove the log was not tampered
- CLI tools to explain, replay, and audit decisions in seconds

---

## CLI tools

### `partenit-why` — explain any decision in plain English

```bash
partenit-why decisions/session_01/

# Output:
# ╭─ Decision Explanation ──────────────────────────────╮
# │  Action : navigate_to(zone='C2', speed=2.0)         │
# │  Time   : 2026-03-08 14:23:41 UTC                   │
# │  Status : ● BLOCKED   Risk score: 0.92              │
# │                                                      │
# │  Why BLOCKED:                                        │
# │    → Rule fired: emergency_stop                      │
# │                                                      │
# │  Risk contributors:                                  │
# │    human_distance              0.85  ████████████   │
# │    speed                       0.45  ███████        │
# │                                                      │
# │  Fingerprint: ✓ VALID                               │
# ╰──────────────────────────────────────────────────────╯
```

Works with a JSON file, JSONL log, or decisions directory.
Also available as: `partenit-log why <path>`

---

### `partenit-watch` — live monitor of guard decisions

```bash
partenit-watch decisions/

# ┌─ Partenit Guard Monitor ─── session_01 ─── total=24 blocked=1 modified=6 ─┐
# │  Time      Status     Action              Risk  Policies / Reason           │
# │  14:23:41  BLOCKED    navigate_to         0.92  emergency_stop              │
# │  14:23:39  MODIFIED   navigate_to         0.64  human_proximity_slowdown    │
# │  14:23:35  ALLOWED    navigate_to         0.12                              │
# └────────────────────────────────────────────────────────────────────────────┘
```

Refreshes every 500ms as new decisions arrive. Ctrl+C to stop.
Also available as: `partenit-log watch <path>`

---

### `partenit-log replay` — timeline of a full session

```bash
partenit-log replay decisions/session_01/
partenit-log replay decisions/session_01/ --output replay.html
```

Terminal view (rich table) or HTML report with a colour-coded timeline.

---

### `partenit-log verify` — check fingerprint integrity

```bash
partenit-log verify decisions/session_01/
# Verified 42 packets: 42 valid, 0 tampered
# OK: all packets verified
```

---

### `partenit-log inspect` — full JSON dump of a packet

```bash
partenit-log inspect <packet_id> --storage-dir decisions/
```

---

### `partenit-record` — session management

```bash
partenit-record list                     # list all recorded sessions
partenit-record show session_01          # session summary
partenit-record export session_01        # export to single JSON
```

---

## Python API

```python
from partenit.decision_log import DecisionLogger

logger = DecisionLogger(storage_dir="./decisions/", session_name="warehouse_run")

packet = logger.create_packet(
    action="navigate_to",
    params={"zone": "shipping", "speed": 1.5},
    guard_decision=decision,
    observations=obs,
)

# Verify fingerprint
assert logger.verify_packet(packet)

# Query history
packets = logger.recent(10)
```

### Storage backends

```python
from partenit.decision_log import DecisionLogger, InMemoryStorage

# Disk storage (default)
logger = DecisionLogger(storage_dir="./decisions/")

# In-memory (for tests and short runs)
logger = DecisionLogger(storage=InMemoryStorage())

# Custom backend
class MyStorage(DecisionStorage):
    def write(self, packet): ...
    def read_all(self): ...

logger = DecisionLogger(storage=MyStorage())
```

---

## DecisionPacket format

Every packet contains:

| Field | Description |
|---|---|
| `packet_id` | UUID |
| `timestamp` | UTC datetime |
| `action_requested` | Action name |
| `action_params` | Original parameters |
| `guard_decision` | Allowed / blocked / modified + reason + risk |
| `applied_policies` | Which rules fired |
| `observation_hashes` | SHA-256 of sensor inputs |
| `fingerprint` | SHA-256 of entire packet |

JSON Schema: [`/schemas/DecisionPacket.schema.json`](../../../schemas/DecisionPacket.schema.json)

---

[Documentation](../../../docs/) · [Examples](../../../examples/) · [Issues](https://github.com/GradeBuilderSL/partenit/issues)
