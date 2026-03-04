[<img src="../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

## Partenit Analyzer — Frontend

**Purpose:** React + TypeScript + Vite + Tailwind + shadcn/ui frontend for visualizing:
- guard decisions and risk scores
- trust state per sensor and object
- active policies and their activity
- scenario replays and live guard checks

Planned pages:
- **Dashboard** — overview metrics and risk timeline
- **Decision Inspector** — deep dive into a single `DecisionPacket`
- **Policy Viewer** — list and filter active policies, highlight conflicts
- **Trust Monitor** — sensor trust gauges and history
- **Scenario Replayer** — step through simulation results
- **Live Guard Tester** — interactive form calling `/guard/check`

The frontend will be launched together with the backend via `docker-compose` in the `analyzer/` directory.

[<img src="../../partenit_robot.png" alt="Partenit robot" width="320" />](https://partenit.io)

Made with love for the future at [Partenit](https://partenit.io).

