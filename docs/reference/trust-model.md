[<img src="../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

## Trust Model Reference

This document explains how `partenit-trust-engine` models:

- sensor trust degradation (`SensorTrustModel`)
- object confidence decay (`ObjectConfidenceModel`)
- trust modes (`nominal`, `degraded`, `unreliable`, `failed`)
- how these values feed into risk scoring and guard decisions

The authoritative implementation lives in `partenit.trust_engine`.

---

## SensorTrustModel

`SensorTrustModel` tracks a **trust score per sensor** in \([0.0, 1.0]\).

Update rule (conceptually):

\[
\text{Trust}(t+1) = \text{Trust}(t) \cdot \text{decay\_factor} + \text{reinforcement}
\]

Where:

- `decay_factor ∈ (0, 1]` decreases when degradation signals are present:
  - high `depth_variance`
  - poor `lighting_quality`
  - low `detection_consistency`
  - spikes in `noise_spikes`
  - `frame_rate_drops`
- `reinforcement ≥ 0` is a small positive term added when readings are consistent and healthy.

### Trust modes

The numeric trust value is mapped to a discrete `TrustMode`:

```python
from partenit.core.models import TrustMode

if trust > 0.8:
    mode = TrustMode.NOMINAL
elif trust > 0.5:
    mode = TrustMode.DEGRADED
elif trust > 0.2:
    mode = TrustMode.UNRELIABLE
else:
    mode = TrustMode.FAILED
```

These thresholds are baked into `TrustMode.from_value()` in `partenit-core`.

In code you typically interact with `TrustState`:

```python
from partenit.trust_engine import SensorTrustModel

model = SensorTrustModel(sensor_id="realsense_front")

model.update(
    depth_variance=0.03,
    lighting_quality=0.7,
    detection_consistency=0.9,
    noise_spikes=0.1,
    frame_rate_drops=0.0,
)

state = model.get_state()
print(state.trust_value, state.mode)
# 0.92, TrustMode.NOMINAL (for example)
```

Guard and risk engines can then:

- down-weight observations from degraded sensors,
- trigger `SafetyEvent` with `event_type="sensor_degraded"` or `TRUST_FAILED`,
- increase risk when trust is low during high-speed actions.

---

## ObjectConfidenceModel

`ObjectConfidenceModel` tracks **per-object confidence** over time.
Confidence decays when an object is not observed for a while:

\[
\text{confidence}(t) = \text{confidence}(t_0) \cdot e^{-\lambda \cdot (t - t_0)}
\]

Where:

- \(t_0\) — last time the object was confidently observed.
- `lambda` — decay rate, configurable per object class:
  - higher for humans (they move quickly),
  - lower for static obstacles or walls.

Example:

```python
from partenit.trust_engine import ObjectConfidenceModel

conf = ObjectConfidenceModel()
conf.observe("human_42", cls="human", confidence=0.9)

# ... some seconds later, without new detections ...
current = conf.get("human_42")
print(current.value, current.location_uncertain)
```

When confidence drops below `0.1`, the engine marks:

- `location_uncertain = True` on the derived `StructuredObservation`,
- which is then propagated via `StructuredObservation.location_uncertain`.

In policy / risk logic this usually means **“assume the human might still be there”**,
not that the human disappeared.

---

## How trust feeds into risk and decisions

Trust and confidence affect guard decisions in several ways:

- Low `sensor_trust`:
  - increases risk when high-speed actions are requested,
  - can trigger slowdown / stop policies even if no explicit human is seen,
  - may emit `SafetyEvent` with `SENSOR_DEGRADED` or `TRUST_FAILED`.

- Low object confidence:
  - sets `location_uncertain=True`,
  - policies can treat “uncertain human” as present (conservative assumption),
  - risk scoring may add a penalty term for operating near uncertain regions.

Example guard logic pattern (simplified):

```python
if trust_state.mode in {TrustMode.UNRELIABLE, TrustMode.FAILED}:
    # Clamp speed regardless of nominal distance
    params["speed"] = min(params.get("speed", 0.5), 0.3)
```

The exact numeric contributions live in `partenit.trust_engine` and
`partenit.agent_guard.risk`, but the qualitative behavior is:

- **uncertainty → more conservative behavior**, never the opposite.

---

## Design principles

- **Monotonic safety**: degradation of trust can only increase risk or reduce admissible behavior.
- **Explainability**: each change in trust or confidence can be traced back to measurable signals.
- **Vendor-agnostic**: trust inputs are generic (variance, consistency, rate) and do not depend on a specific sensor brand.

Together with `DecisionPacket`, the trust model ensures that you can answer:

> “Which sensors were trusted at the moment of this decision, and why did the guard
> choose to stop/slow down?”

