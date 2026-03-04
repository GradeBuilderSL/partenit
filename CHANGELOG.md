# Changelog

All notable changes to Partenit open-source packages are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- `MockWorld.set_trust_profile()` — global sensor trust degradation profile
  with linear interpolation over time.
- `MockWorld.get_global_sensor_trust()` — interpolated trust value at
  current simulation time.
- `MockWorld.get_context()` now exposes `sensor_trust`, `human.sensor_trust`,
  and `human.confidence` (trust-weighted) in the context dict.
- `ScenarioConfig.sensor_trust_profile` field — parsed from
  `world.sensor_trust_profile` in scenario YAML.
- `ScenarioResult.trust_curve` — per-tick `(time, global_trust)` timeseries.
- `MockRobot` speed restoration: when the guard allows an action without
  clamping speed, the robot restores its `current_speed` to `initial_speed`.
- `DecisionStorage` abstract base class in `partenit-decision-log` — common
  interface for all storage backends (`write`, `read_all`, `list_dates`).
- `InMemoryStorage` — ephemeral in-memory backend; no disk writes.
  Useful for tests and short-lived bench runs.
- `DecisionLogger(storage=...)` keyword argument — pass any `DecisionStorage`
  implementation directly, bypassing `storage_dir`.
- `LocalFileStorage` now inherits from `DecisionStorage`.
- HTML report: admissibility score progress bar (colour-coded).
- HTML report: trust curve chart shown when trust degrades below 0.99.
- HTML report: collapsible sections (`<details>`) for charts, event log,
  and policy fire log.
- HTML report: event log rows are colour-highlighted by event type
  (stop = red tint, slowdown = amber tint).
- HTML report: slowdown markers (amber dots) on 2D trajectory replay.
- HTML report: matched/missed expected-event summary shown per run.
- HTML report: policy fire log increased from 40 to 60 entries.
- `examples/ros2_demo.py` — runnable ROS2 guard demo with graceful
  `ImportError` fallback when `rclpy` is not available.

### Changed
- `MockRobot.step()`: speed clamp is now applied even when the new speed
  equals the current speed (previously only on strict decrease).
  Stop events are unchanged.
- HTML report legend for 2D replay now includes slowdown dot marker.

---

## [0.1.0] — Initial open release

### Packages
- `partenit-core` 0.1.0 — shared types: `StructuredObservation`,
  `PolicyRule`, `PolicyBundle`, `GuardDecision`, `RiskScore`, `TrustState`,
  `SafetyEvent`, `DecisionPacket`, `DecisionFingerprint`.
- `partenit-policy-dsl` 0.1.0 — YAML policy language, parser, validator,
  conflict checker, and CLI (`partenit-policy`).
- `partenit-trust-engine` 0.1.0 — `SensorTrustModel`, `ObjectConfidenceModel`,
  conformal prediction bridge (`treat_as_human` flag).
- `partenit-agent-guard` 0.1.0 — `AgentGuard` action safety middleware,
  priority-based conflict resolution, risk scoring.
- `partenit-safety-bench` 0.1.0 — `ScenarioRunner`, `MockWorld`, `MockRobot`,
  `BenchmarkRunner`, HTML report generator, CLI (`partenit-bench`).
  Built-in scenarios: `human_crossing_path`, `blind_spot`,
  `sensor_degradation`, `policy_conflict_determinism`,
  `llm_unsafe_command`, `cross_adapter_determinism`.
- `partenit-decision-log` 0.1.0 — `DecisionLogger`, `LocalFileStorage`,
  `DecisionArchive`, SHA-256 fingerprint verification, CLI (`partenit-log`).
- `partenit-adapters` 0.1.0 — `MockRobotAdapter`, `HTTPRobotAdapter`
  (with circuit breaker), `ROS2Adapter`, `IsaacSimAdapter`, `UnitreeAdapter`,
  `GazeboAdapter`, `LLMToolCallGuard`.

### Infrastructure
- Analyzer web UI: FastAPI backend + React/TypeScript/Vite frontend.
- Prometheus metrics endpoint (`/metrics`), Grafana dashboard config.
- GitHub Actions CI (`python -m pytest`, ruff lint, schema validation).
- JSON Schemas: `DecisionPacket.schema.json`, `DecisionFingerprint.schema.json`.
- OpenAPI spec: `robot-adapter-api.yaml`.
- Documentation: getting started, simulation guide, ROS2 guide,
  custom robot guide, LLM agent guide, writing policies guide,
  DecisionPacket reference, trust model reference, vendor spec.
