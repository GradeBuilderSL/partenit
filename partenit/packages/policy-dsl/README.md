[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# partenit-policy-dsl

> **Safety policies as code. Written by safety engineers, enforced by the guard.**

YAML-based policy language for defining robot safety rules.
Policies are validated, versioned, and loaded by `AgentGuard` at runtime.

```bash
pip install partenit-policy-dsl
```

---

## Policy format

```yaml
rule_id: human_proximity_slowdown
name: "Human Proximity Speed Limit"
priority: safety_critical        # safety_critical | legal | task | efficiency
provenance: "ISO 3691-4 section 5.2"
condition:
  type: threshold
  metric: human.distance
  operator: less_than
  value: 1.5
  unit: meters
action:
  type: clamp
  parameter: max_velocity
  value: 0.3
  unit: m/s
```

Priority hierarchy: `safety_critical > legal > task > efficiency`
Higher priority always wins. Deterministic and logged.

---

## CLI tools

### `partenit-init` — scaffold a new project

```bash
partenit-init my_robot
```

```
  ✓ policies/policies.yaml
  ✓ decisions/
  ✓ main.py
  ✓ .gitignore

╭─ my_robot is ready! ────────────────────────╮
│  cd my_robot                                │
│  pip install partenit                       │
│  python main.py                             │
╰─────────────────────────────────────────────╯
```

Creates: starter safety policies, a `GuardedRobot` quickstart script,
an empty `decisions/` directory, and a `.gitignore`.

---

### `partenit-policy validate` — check for errors

```bash
partenit-policy validate ./policies/
# OK: validation passed (0 warnings)
```

### `partenit-policy check-conflicts` — detect conflicting rules

```bash
partenit-policy check-conflicts ./policies/
# Found 1 conflict:
#   human_proximity_slowdown ↔ emergency_stop: overlapping conditions
```

### `partenit-policy sim` — test a policy without a robot

```bash
partenit-policy sim \
    --action navigate_to \
    --speed 2.0 \
    --human-distance 1.2 \
    --policy-path ./examples/warehouse/policies.yaml

# Policy Simulator
# ┌─────────────────────────────────┬──────────────────┬────────┬────────────────┐
# │ Rule                            │ Priority         │ Status │ Effect         │
# │ Human Proximity Speed Limit     │ safety_critical  │ FIRED  │ clamp speed→0.3│
# │ Emergency Stop                  │ safety_critical  │ –      │                │
# └─────────────────────────────────┴──────────────────┴────────┴────────────────┘
# Result: ALLOWED (modified)
#   max_velocity → 0.3
```

### `partenit-policy diff` — compare two policy configurations

```bash
partenit-policy diff policies/v1.yaml policies/v2.yaml

# ── Policy Diff  v1.yaml → v2.yaml ──────────────────────────────
# Rules: 4 → 5  (+1 added  -0 removed  ~1 changed)
#
# Added rules:
#   + extended_slowdown_zone  [safety_critical]  Extended proximity zone
#
# Changed rules:
#   ~ human_proximity_slowdown
#       action.value: 0.3 → 0.2
```

With scenario comparison (requires `partenit-safety-bench`):

```bash
partenit-policy diff policies/v1.yaml policies/v2.yaml \
    --scenario examples/benchmarks/human_crossing_path.yaml

# ── Scenario impact  human_crossing_path ────────────────────────
# ┌────────────────────────┬───────────┬───────────┬──────────┐
# │ Metric                 │ v1.yaml   │ v2.yaml   │ Change   │
# │ Safety grade           │ B+        │ A-        │ improved │
# │ Overall score          │ 0.79      │ 0.88      │ ↑ 0.09   │
# │ Collision rate         │ 8%        │ 2%        │ ↓ 6%     │
# │ Task completion        │ 100%      │ 100%      │ =        │
# └────────────────────────┴───────────┴───────────┴──────────┘
```

### `partenit-policy bundle` — create a versioned bundle

```bash
partenit-policy bundle ./policies/ --output bundle.json --version 1.2.0
# Bundle: 5 rules → bundle.json
# Hash:   sha256:abc123...
```

---

## Python API

```python
from partenit.policy_dsl import PolicyParser, PolicyBundleBuilder

# Load rules
parser = PolicyParser()
rules = parser.load_dir("./policies/")

# Build a versioned bundle
builder = PolicyBundleBuilder()
bundle = builder.from_dir("./policies/", version="1.0.0")

# Load into guard
from partenit.agent_guard import AgentGuard
guard = AgentGuard()
guard.load_bundle(bundle)
```

---

## Writing policies

See [docs/guides/writing-policies.md](../../../docs/guides/writing-policies.md)
for a full reference including:
- All condition types (`threshold`, `compound`)
- All action types (`clamp`, `block`, `rewrite`)
- Release conditions
- Conflict detection rules
- Priority semantics

Example policies: [examples/warehouse/policies.yaml](../../../examples/warehouse/policies.yaml)

---

[Documentation](../../../docs/) · [Examples](../../../examples/) · [Issues](https://github.com/GradeBuilderSL/partenit/issues)
