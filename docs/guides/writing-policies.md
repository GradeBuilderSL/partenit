[<img src="../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# Writing Safety Policies

This guide is for safety engineers and domain experts. No programming experience needed.

Policies are plain YAML files. They describe *when* to intervene and *what* to do.
Developers load them into the guard — you do not need to touch any Python code.

---

## One policy, one file

Each policy rule lives in its own YAML file (or grouped in a single file with a `rules:` list).

```yaml
rule_id: human_proximity_slowdown
name: "Human Proximity Speed Limit"
priority: safety_critical
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

---

## The four building blocks

### 1. `rule_id` and `name`

Every rule needs a unique `rule_id` (no spaces, use underscores) and a human-readable `name`.

```yaml
rule_id: emergency_stop_near_human
name: "Emergency stop when human is too close"
```

### 2. `priority`

Priority resolves conflicts when two rules fire simultaneously.

| Priority | Numeric | When to use |
|---|---|---|
| `safety_critical` | 1000 | Physical harm prevention |
| `legal` | 500 | Regulatory compliance (ISO, CE, local law) |
| `task` | 100 | Mission objectives |
| `efficiency` | 10 | Nice-to-have optimizations |

**Higher priority always wins.** This is deterministic and logged in the `DecisionPacket`.

```yaml
priority: safety_critical
```

### 3. `condition` — when does the rule apply?

#### Threshold condition

Fires when a metric crosses a threshold.

```yaml
condition:
  type: threshold
  metric: human.distance       # dot-notation into the context
  operator: less_than          # less_than | greater_than | equal_to
  value: 1.5
  unit: meters                 # optional, for documentation
```

Available operators: `less_than`, `greater_than`, `equal_to`, `less_than_or_equal`, `greater_than_or_equal`

#### Compound condition (AND / OR)

```yaml
condition:
  type: compound
  operator: and                # and | or
  conditions:
    - type: threshold
      metric: human.distance
      operator: less_than
      value: 2.0
    - type: threshold
      metric: speed
      operator: greater_than
      value: 0.5
```

#### What metrics are available?

The context dict is built from sensor observations and the world state:

| Metric | Example value | Meaning |
|---|---|---|
| `human.distance` | `1.2` | Distance in meters to nearest detected human |
| `speed` | `2.0` | Current requested speed in m/s |
| `trust.depth_camera` | `0.7` | Trust level of depth camera (0-1) |
| `zone` | `"restricted"` | Current or target zone name |

Add custom metrics by passing them in the `context` dict from your code.

### 4. `action` — what happens when the rule fires?

#### Clamp a parameter

Reduce a numeric parameter to a maximum safe value. The robot still moves — just slower.

```yaml
action:
  type: clamp
  parameter: max_velocity      # name of the parameter in the action call
  value: 0.3
  unit: m/s
```

#### Block the action entirely

The robot stops. Use only for genuine safety violations.

```yaml
action:
  type: block
  reason: "Human too close — emergency stop required"
```

#### Rewrite a parameter

Replace a parameter with a specific value.

```yaml
action:
  type: rewrite
  parameter: zone
  value: "safe_holding_area"
```

---

## Release conditions

Once a blocking or clamping rule fires, you can specify when to lift it:

```yaml
release:
  type: compound
  conditions:
    - metric: human.distance
      operator: greater_than
      value: 2.0
    - elapsed_seconds: 3        # must stay clear for at least 3 seconds
```

Without a `release` block, the rule lifts automatically on the next evaluation cycle when the condition is no longer met.

---

## Policy provenance

Always include a `provenance` field. It is copied into every `DecisionPacket` and
provides a traceable link from decision to regulation.

```yaml
provenance: "ISO 3691-4 section 5.2 — Industrial trucks: safety requirements for pedestrian-controlled trucks"
```

---

## Full examples

### Warehouse robot

```yaml
# policies/warehouse.yaml
rules:

  - rule_id: human_proximity_slowdown
    name: "Human Proximity Speed Limit"
    priority: safety_critical
    provenance: "ISO 3691-4 §5.2"
    condition:
      type: threshold
      metric: human.distance
      operator: less_than
      value: 1.5
    action:
      type: clamp
      parameter: max_velocity
      value: 0.3

  - rule_id: emergency_stop_at_08m
    name: "Emergency Stop — Human Within 0.8m"
    priority: safety_critical
    provenance: "ISO 3691-4 §5.3"
    condition:
      type: threshold
      metric: human.distance
      operator: less_than
      value: 0.8
    action:
      type: block
      reason: "Human inside minimum safety distance (0.8m)"

  - rule_id: restricted_zone_block
    name: "Block Entry into Restricted Zone"
    priority: legal
    condition:
      type: threshold
      metric: zone
      operator: equal_to
      value: "restricted"
    action:
      type: block
      reason: "Target zone is restricted — manual authorization required"
```

### Hospital delivery robot

```yaml
rules:
  - rule_id: patient_room_slow_speed
    name: "Slow down near patient rooms"
    priority: safety_critical
    condition:
      type: threshold
      metric: zone_type
      operator: equal_to
      value: "patient_room"
    action:
      type: clamp
      parameter: max_velocity
      value: 0.2

  - rule_id: emergency_corridor_priority
    name: "Emergency corridor — yield immediately"
    priority: legal
    condition:
      type: compound
      operator: and
      conditions:
        - metric: zone
          operator: equal_to
          value: "emergency_corridor"
        - metric: emergency_alert
          operator: equal_to
          value: true
    action:
      type: block
      reason: "Emergency corridor active — robot must yield"
```

---

## Validating your policies

From the command line:

```bash
# Validate a single file
partenit-policy validate policies/warehouse.yaml

# Validate an entire directory
partenit-policy validate policies/

# Check for conflicts between rules
partenit-policy check-conflicts policies/

# Bundle all rules into a deployable JSON
partenit-policy bundle policies/ --output bundle.json --version 1.2.0
```

---

## Version control

Policies are plain text. Commit them to Git alongside your code:

```
policies/
├── warehouse.yaml         # main ruleset
├── emergency.yaml         # emergency-only overrides
└── CHANGELOG.md           # who changed what and why
```

Every `DecisionPacket` stores the `policy_bundle_version` — so you can always trace
which version of the policy produced a given decision.

---

## Common mistakes

| Mistake | Fix |
|---|---|
| Two rules with the same `rule_id` | Rule IDs must be unique within a bundle |
| `block` at `efficiency` priority | Block actions should be `safety_critical` or `legal` |
| Missing `provenance` | Always link to the regulation or document that requires this rule |
| Clamp value higher than requested value | Guard only reduces params, never increases them |
| `compound` condition with a single child | Use `threshold` directly instead |
