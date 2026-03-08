# Changelog

All notable changes to Partenit open-source packages are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.2.0] — 2026-03-08

### Added

#### Ergonomics & 1-line API
- `GuardedRobot` class in `partenit-agent-guard` — wraps any `RobotAdapter`
  (duck-typed) with `AgentGuard` + optional `DecisionLogger` in a single object.
  Adds convenience methods `navigate_to()`, `pick_up()`, `stop()`, and
  `execute_action()`. No new hard dependencies on `partenit-adapters`.
- `examples/guarded_robot_demo.py` — 1-line guard integration demo using
  `MockRobotAdapter`.
- `examples/eval_demo.py` — `EvalRunner` comparison demo (baseline vs guarded).

#### CLI tools
- `partenit-log replay` — terminal timeline of decisions from a directory or
  single packet file; optional `--output` writes an HTML replay.
- `partenit-log record` (`partenit-record`) — session management: `list`,
  `show`, `export` subcommands.
- `partenit-policy sim` — dry-run a single action against loaded policies;
  prints a rich table of rule evaluations and final allow/modify/block outcome.
- `partenit-scenario` — alias for `partenit-bench` (user-friendly name).

#### Evaluation platform (`partenit-eval`)
- `EvalRunner` in `partenit-safety-bench` — runs one scenario or a full suite
  against one or more `ControllerConfig` objects and returns `EvalReport`.
- `EvalMetrics` — safety (0.5), efficiency (0.3), AI quality (0.2) subscores
  + weighted `overall_score` + letter grade A–F.
- `partenit-eval run` / `partenit-eval run-suite` CLI with optional HTML report
  and `--compare` controller comparison.
- HTML eval report: grade badge, score breakdown bars, controller comparison
  table, score formula box.

#### Isaac Sim integration
- `examples/isaac_sim/h1_bridge.py` — Omniverse Python bridge for the Unitree
  H1 biped; exposes the standard Partenit HTTP robot API on port 8000.
- `examples/isaac_sim/sim_frontend.py`, `sim_camera.py` — helper scripts for
  the H1 scene (RGB camera, frontend visualisation).
- `examples/isaac_sim/minimal_guard_demo.py` — one-command guard demo that
  connects to the running bridge.
- `examples/test_h1_isaac.py` — 5-step automated test: verifies guard fires,
  speed is clamped, and stop works.
- `examples/isaac_sim/run_bridge.sh` — convenience launcher script.
- `docs/guides/isaac-sim.md` — full guide: architecture, quick start, bridge
  API table.
- `scripts/install.sh` — install all open packages from source in one command.
- Isaac Sim Omniverse Extension template (`partenit-adapters`):
  `partenit/adapters/isaac_sim_extension/` with `extension.py` skeleton and
  `config/extension.toml` manifest.

#### Simulation improvements
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

#### Decision log
- `DecisionStorage` abstract base class — common interface for all storage
  backends (`write`, `read_all`, `list_dates`).
- `InMemoryStorage` — ephemeral in-memory backend; no disk writes. Useful for
  tests and short-lived bench runs.
- `DecisionLogger(storage=...)` keyword argument — pass any `DecisionStorage`
  implementation directly, bypassing `storage_dir`.
- `LocalFileStorage` now inherits from `DecisionStorage`.

#### HTML reports
- Admissibility score progress bar (colour-coded).
- Trust curve chart shown when trust degrades below 0.99.
- Collapsible sections (`<details>`) for charts, event log, and policy fire log.
- Event log rows colour-highlighted by event type (stop = red, slowdown = amber).
- Slowdown markers (amber dots) on 2D trajectory replay.
- Matched/missed expected-event summary shown per run.
- Policy fire log increased from 40 to 60 entries.

#### Other
- `examples/ros2_demo.py` — runnable ROS2 guard demo with graceful
  `ImportError` fallback when `rclpy` is not available.

### Changed
- `MockRobot.step()`: speed clamp is now applied even when the new speed
  equals the current speed (previously only on strict decrease).
  Stop events are unchanged.
- HTML report legend for 2D replay now includes slowdown dot marker.
- `GuardedRobot.execute_action()` always populates `modified_params` before
  calling `adapter.send_decision()`, so adapters always receive concrete
  parameters even when the guard approves without modification.
- README repositioned as "Debugging & Safety Toolkit for Robot AI" with
  updated quickstart using `GuardedRobot`.
- `TESTING_GUIDE_RU.md` extended with sections for all new CLI tools and eval
  workflow.

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
