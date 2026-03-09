# Contributing to Partenit

Thank you for your interest in contributing to the Partenit open-source ecosystem.
This document describes how the project is structured, how to set up a development
environment, and the contribution guidelines.

---

## Project overview

Partenit is a safety and cognitive control layer for physical AI agents.
The repository is a mono-repo of 7 independent Python packages and 1 web UI.

```
partenit/packages/
  core/          — shared types (Pydantic v2, no logic)
  policy-dsl/    — YAML policy language + parser
  trust-engine/  — sensor/object trust degradation
  agent-guard/   — action safety middleware
  safety-bench/  — simulation + benchmarking
  decision-log/  — audit logging + fingerprinting
  adapters/      — robot adapters (Mock, HTTP, ROS2, Isaac, Unitree, Gazebo, LLM)
analyzer/        — FastAPI backend + React frontend
```

**Dependency order** (import lower before upper):
```
core → policy-dsl, trust-engine → agent-guard, adapters → safety-bench, decision-log
```

---

## Development setup

```bash
# Clone the repo
git clone https://github.com/GradeBuilderSL/partenit.git
cd partenit

# Install all packages in editable mode (or run ./scripts/install.sh from repo root)
pip install -e partenit/packages/core
pip install -e partenit/packages/policy-dsl
pip install -e partenit/packages/trust-engine
pip install -e partenit/packages/agent-guard
pip install -e partenit/packages/adapters
pip install -e partenit/packages/safety-bench
pip install -e partenit/packages/decision-log

# Install dev dependencies
pip install pytest ruff pyyaml jsonlines httpx respx rich numpy
```

### Run tests
```bash
python -m pytest partenit/ tests/ -q
```

### Lint
```bash
ruff check partenit/
```

---

## Package conventions

### Python style
- Python 3.10+, all public functions must have type hints.
- Pydantic v2 for all data models — no exceptions.
- No print statements in library code; use `logging`.
- Line length limit: 100 (enforced by ruff, E501 is ignored in IDE).

### Package structure
Each package under `partenit/packages/` must have:
- `pyproject.toml` with `[project]`, `[build-system]` (hatchling), and `[tool.ruff]`.
- `src/partenit/<package_name>/` layout (no top-level `__init__.py` at src/).
- `tests/` directory with pytest tests.
- `README.md` with a one-paragraph summary and install command.

### Testing
- Target >80% coverage per package.
- Every new public function should have at least one test.
- Determinism tests: if a function is deterministic, verify it produces
  identical output across repeated calls with the same seed.

---

## Architecture rules — do not violate these

1. **No safety logic in adapters.** Adapters are thin translation layers.
   All risk scoring, policy evaluation, and trust computation lives in
   `agent-guard`, `policy-dsl`, `trust-engine`.

2. **No breaking changes to public contracts:**
   - `DecisionPacket` schema (`/schemas/DecisionPacket.schema.json`)
   - `RobotAdapter` interface (`adapters/base.py`)
   - `PolicyRule` schema
   - CLI command signatures (`partenit-bench`, `partenit-policy`, `partenit-log`)

   Deprecate with a warning, remove only in next major version.

3. **`DecisionPacket` must always be created — even on safe stop.**
   There is no code path in `decision-log` that skips logging.

4. **Adapters must degrade gracefully.** Optional dependencies (`rclpy`,
   `isaaclab`, etc.) must raise `ImportError` with a clear message, not crash.

5. **No new external dependencies without discussion.** The dependency list
   in `CLAUDE.md` is intentional. Keep packages minimal.

---

## What lives in open vs enterprise

**Open (this repo, contributions welcome):**
- All 7 packages listed above
- Basic risk scoring (distance + velocity + trust)
- MockRobot / HTTP / ROS2 / Isaac / Unitree / Gazebo / LLM adapters
- Safety bench + scenario format
- Decision log + SHA-256 fingerprinting
- Analyzer web UI
- JSON Schemas

**Enterprise (closed, not accepting contributions):**
- Conformal prediction with coverage guarantees
- Plan-conditional risk scoring
- GraphRAG policy retrieval
- Formal verification (CBF/STL)
- Fleet coordination + policy broadcast
- Cloud sync + managed storage
- Compliance export (ISO/audit)
- Hardware licensing

If your contribution relates to enterprise features, please open an issue
to discuss before investing time in implementation.

---

## Submitting changes

1. Fork the repository and create a branch: `git checkout -b feat/my-feature`.
2. Make your changes. Add tests.
3. Run `python -m pytest partenit/ tests/ -q` and `ruff check partenit/`.
4. Open a pull request with a clear description of:
   - What problem does this solve?
   - Which packages are affected?
   - Does this change any public contracts?
5. PRs that change `DecisionPacket` schema must include a migration note
   in `CHANGELOG.md` and a schema version bump.

---

## Reporting bugs

Open an issue on GitHub with:
- Python version, OS, package versions (`pip list | grep partenit`)
- Minimal reproducible example
- Actual vs expected behaviour

---

## Questions and discussions

Open a GitHub Discussion for design questions, feature proposals, or
integration use cases. Issues are for confirmed bugs and actionable tasks.
