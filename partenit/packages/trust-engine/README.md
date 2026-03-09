[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

# partenit-trust-engine

> **Sensors lie. Trust degrades. The guard compensates.**

`partenit-trust-engine` tracks how much to trust each sensor and each detected object
over time. When trust drops, the guard automatically becomes more conservative.

```bash
pip install partenit-trust-engine
```

---

## Why this matters

A LiDAR in low lighting gives unreliable depth readings.
A human detection 3 seconds ago may no longer be valid.
Without trust modelling, your guard reacts to stale or noisy data as if it were truth.

`partenit-trust-engine` solves this by degrading confidence over time
and signalling the guard to act conservatively under uncertainty.

---

## Sensor trust — `SensorTrustModel`

Tracks trust level per sensor. Degrades on signal quality issues, recovers when signal stabilises.

```python
from partenit.trust_engine import SensorTrustModel, SensorSignal

model = SensorTrustModel(sensor_id="depth_camera", initial_trust=1.0)

# Feed a signal reading
signal = SensorSignal(
    depth_variance=0.15,   # high variance → degrade
    frame_rate=28.0,       # nominal
    noise_level=0.05,
)
model.update(signal)

print(model.trust_level)   # e.g. 0.73
print(model.mode)          # TrustMode.DEGRADED
print(model.reasons)       # ["depth_variance_spike"]
```

### Trust formula

```
Trust(t+1) = Trust(t) * decay_factor + reinforcement
```

Degradation triggers:
- `depth_variance` spike above threshold
- Low lighting (low frame rate or signal confidence)
- Inconsistent detections
- Frame rate drops

### Trust modes

| Mode | Range | Guard behaviour |
|---|---|---|
| `NOMINAL` | > 0.8 | Normal operation |
| `DEGRADED` | 0.5 – 0.8 | Guard applies tighter thresholds |
| `UNRELIABLE` | 0.2 – 0.5 | Guard assumes worst-case distances |
| `FAILED` | < 0.2 | Guard stops robot until sensor recovers |

---

## Object confidence — `ObjectConfidenceModel`

Tracks how confident we are in each detected object's current position.
Confidence decays exponentially when an object is not seen.

```python
from partenit.trust_engine import ObjectConfidenceModel

model = ObjectConfidenceModel(decay_lambda=0.3)  # humans decay fast

# Object observed at t=0
model.observe("human-01", class_name="human", confidence=0.91, timestamp=0.0)

# 2 seconds later, no new observation
conf = model.get_confidence("human-01", current_time=2.0)
print(conf)   # 0.55 — still tracked but decaying

# 8 seconds later
conf = model.get_confidence("human-01", current_time=8.0)
print(conf)   # 0.09 — below 0.1 → location_uncertain = True
```

### Decay formula

```
confidence(t) = confidence(t0) * exp(-lambda * time_since_seen)
```

`lambda` is configurable per object class. Humans decay faster than static obstacles.
Below 0.1 → the object is marked `location_uncertain` and treated as if
it could be anywhere within the last known area.

---

## Conformal prediction bridge — `ConformalBridge`

Converts raw model scores into conservative prediction sets.
If `"human"` appears in the prediction set, `treat_as_human = True` is forced.

```python
from partenit.trust_engine import ConformalBridge

bridge = ConformalBridge(coverage=0.9)

# Detector output: softmax probabilities per class
scores = {"human": 0.62, "obstacle": 0.31, "empty": 0.07}
prediction_set = bridge.predict_set(scores)

print(prediction_set)         # {"human", "obstacle"}
print("human" in prediction_set)  # True → guard treats as human
```

Conservative by design: uncertainty resolves toward safety.

---

## Integration with the guard

The trust engine feeds into `StructuredObservation` which the guard reads:

```python
from partenit.core.models import StructuredObservation

obs = StructuredObservation(
    object_id="human-01",
    class_name="human",
    distance_m=1.8,
    confidence=0.55,          # from ObjectConfidenceModel
    sensor_trust=0.73,        # from SensorTrustModel
    treat_as_human=True,      # forced by ConformalBridge
)
# Guard will apply human-proximity policies even at confidence 0.55
```

The guard interprets low sensor trust by shrinking effective distance thresholds:
if trust is 0.6, a human at 1.8 m is treated as if it were at 1.8 * 0.6 = 1.08 m.

---

## Dependencies

```
pydantic >= 2.0
numpy
partenit-core >= 0.1.0
```

---

[Documentation](../../../docs/) · [Examples](../../../examples/) · [Issues](https://github.com/GradeBuilderSL/partenit/issues)
