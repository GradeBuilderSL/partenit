[<img src="../../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

## partenit-trust-engine

**Purpose:** model trust degradation for sensors and world objects over time, and provide a simple conformal prediction bridge.

This package will include:
- `SensorTrustModel` — tracks per-sensor trust level based on signal quality.
- `ObjectConfidenceModel` — decays object confidence over time when not observed.
- `ConformalPredictionBridge` — converts model scores into conservative prediction sets.

It will depend on:
- `partenit-core` for `TrustState` and related types.
- `numpy` and `pydantic` for numerical routines and data models.

Design details and formulas are described in `IMPLEMENTATION_PLAN.md`.  
Usage examples will be added once the public API stabilizes.

[<img src="../../../partenit_robot.png" alt="Partenit robot" width="320" />](https://partenit.io)

Made with love for the future at [Partenit](https://partenit.io).

