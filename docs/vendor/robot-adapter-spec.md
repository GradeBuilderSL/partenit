[<img src="../../partenit.png" alt="Partenit logo" width="220" />](https://partenit.io)

## Robot Adapter Vendor Specification

This document defines the **formal integration contract** for robot vendors who want
to connect their systems to Partenit via the HTTP adapter (`HTTPRobotAdapter`).

The machine-readable OpenAPI document lives at:

- `schemas/robot-adapter-api.yaml`

This page is the human-readable companion.

---

## 1. Overview

Your robot (or a gateway service next to it) MUST implement three endpoints:

| Method | Path                     | Description                                  |
|--------|--------------------------|----------------------------------------------|
| GET    | `/partenit/observations` | Return current sensor observations           |
| POST   | `/partenit/command`      | Accept and execute a GuardDecision           |
| GET    | `/partenit/health`       | Report robot / adapter health status         |

All endpoints use JSON over HTTP/1.1 or HTTP/2.

- Authentication (if needed) should use HTTP headers (e.g. `Authorization`).
- TLS is recommended for production deployments.

---

## 2. `/partenit/observations`

### 2.1 Request

**Method:** `GET`  
**Query parameters:** none required.

### 2.2 Response

**Status:** `200 OK`  
**Body:** JSON array of `StructuredObservation` objects.

Each element MUST conform to `partenit.core.models.StructuredObservation`:

```json
[
  {
    "object_id": "worker-1",
    "class_best": "human",
    "class_set": ["human"],
    "position_3d": [1.2, 0.0, 0.0],
    "velocity": [0.0, 0.0, 0.0],
    "confidence": 0.93,
    "depth_variance": 0.02,
    "sensor_trust": 0.95,
    "timestamp": "2025-01-01T12:00:00Z",
    "frame_hash": "e3b0c44298fc1c149afbf4c8...",
    "source_id": "front_camera"
  }
]
```

**Notes:**

- `class_set` SHOULD contain `"human"` if there is any chance the object is a human.
- `position_3d` is in meters, robot-centric.
- `frame_hash` is optional but strongly recommended for auditability.

### 2.3 Error handling

- `5xx` codes indicate temporary backend/sensor issues.
- `4xx` codes SHOULD NOT be used for normal “no object” situations — return an empty array instead.

---

## 3. `/partenit/command`

### 3.1 Request

**Method:** `POST`  
**Body:** JSON representation of `GuardDecision` from `partenit-core` / `partenit-agent-guard`.

Example:

```json
{
  "allowed": true,
  "modified_params": {"zone": "A3", "speed": 0.3},
  "rejection_reason": null,
  "risk_score": {
    "value": 0.21,
    "contributors": {"distance": 0.15, "speed": 0.06},
    "plan_id": null,
    "timestamp": "2025-01-01T12:00:00Z"
  },
  "applied_policies": ["human_proximity_slowdown"],
  "suggested_alternative": null,
  "timestamp": "2025-01-01T12:00:00Z",
  "latency_ms": 2.7
}
```

Your implementation MUST:

- Execute the command described by `modified_params` if `allowed=true`.
- Refrain from executing the original unsafe command if `allowed=false`.
- Optionally log or surface `rejection_reason` and `applied_policies` to operators.

### 3.2 Response

On success:

- `200 OK`
- Body:

```json
{
  "status": "ok"
}
```

On failure to execute the command:

- `500 Internal Server Error` (or a more specific `5xx`)
- Body SHOULD include a machine-readable error code and human-readable message.

Example:

```json
{
  "status": "error",
  "code": "ACTUATOR_TIMEOUT",
  "message": "Motion controller did not respond within 200 ms."
}
```

---

## 4. `/partenit/health`

### 4.1 Request

**Method:** `GET`  
**Query parameters:** none.

### 4.2 Response

**Status:** `200 OK`  
**Body:**

```json
{
  "status": "ok",
  "robot_id": "robot-123",
  "timestamp": "2025-01-01T12:00:00Z"
}
```

Additional optional fields:

- `mode` — `"auto" | "manual" | "e_stop" | ..."`
- `battery` — battery percentage (0–100)
- `errors` — list of active error codes

The `status` field SHOULD be one of:

- `"ok"` — robot ready to accept commands
- `"degraded"` — robot can move but has warnings (e.g. low battery)
- `"unreachable"` — used by the adapter when your endpoint cannot be contacted

---

## 5. Versioning and compatibility

- The canonical schemas derive from:
  - `partenit.core.models.StructuredObservation`
  - `partenit.core.models.GuardDecision` / `RiskScore`
- Breaking changes to these types require a **major** version bump of Partenit.
- Vendors SHOULD:
  - tolerate additional unknown fields (forward compatibility),
  - avoid removing or renaming existing fields.

When upgrading Partenit, run:

- `partenit-schema export --output ./schemas/`

and compare the new JSON Schema with your integration.

---

## 6. Example implementation patterns

- **Gateway pattern:** run a small HTTP service in front of the robot controller that:
  - reads robot state from PLC / fieldbus / vendor SDK,
  - converts it to `StructuredObservation`,
  - accepts `GuardDecision` and translates it into motion commands.

- **Sidecar pattern:** for robots that already have an HTTP API:
  - implement a thin sidecar that adapts between your native API and the Partenit contract.

In both cases the business logic of your robot remains unchanged — Partenit acts as
a **safety and audit layer** around it.

---

## 7. Test procedures

To validate a vendor implementation:

1. Start the robot HTTP server in a non-destructive test mode.
2. Use `HTTPRobotAdapter` from a Python script to:
   - call `/partenit/health` and verify fields,
   - call `/partenit/observations` and check JSON structure,
   - send a benign `GuardDecision` via `/partenit/command`.
3. Run a simple `partenit-safety-bench` scenario with `HTTPRobotAdapter`.
4. Verify that:
   - unsafe commands are blocked or clamped as expected,
   - `DecisionPacket` logs are created and verifiable,
   - robot responds correctly to allowed commands.

