[<img src="../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

## Partenit Analyzer — Backend

**Purpose:** FastAPI-based backend that exposes APIs for:
- querying decisions from `partenit-decision-log`
- inspecting trust state from `partenit-trust-engine`
- listing active policies and scenario results
- performing live guard checks via `partenit-agent-guard`

Planned responsibilities:
- Provide REST endpoints:
  - `GET /decisions`
  - `GET /decisions/{packet_id}`
  - `GET /trust/current`
  - `GET /trust/history`
  - `GET /policies/active`
  - `GET /scenarios/results`
  - `POST /guard/check`
  - `GET /health`
- Serve as a data source for the React frontend in `../frontend`.

Implementation details will follow the design captured in `IMPLEMENTATION_PLAN.md`.

[<img src="../../partenit_robot.png" alt="Partenit robot" width="320" />](https://partenit.io)

Made with love for the future at [Partenit](https://partenit.io).

