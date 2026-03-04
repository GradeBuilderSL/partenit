"""
Tests for the Partenit Analyzer backend API.

Uses FastAPI TestClient (httpx-based synchronous client).
All tests run without a real robot, simulator, or database —
the backend's in-memory state is used throughout.
"""

from __future__ import annotations

import textwrap

import pytest
from fastapi.testclient import TestClient

from partenit.analyzer.backend.main import app
from partenit.analyzer.backend.state import get_state, AppState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Reset backend singleton state before each test.

    Replaces the module-level _state so each test starts clean.
    """
    fresh = AppState()
    import partenit.analyzer.backend.state as state_mod
    monkeypatch.setattr(state_mod, "_state", fresh)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def client_with_policies(client: TestClient, tmp_path) -> TestClient:
    """Client with a simple blocking policy pre-loaded."""
    policy_yaml = textwrap.dedent("""\
        rule_id: emergency_stop
        name: Emergency Stop
        priority: safety_critical
        condition:
          type: threshold
          metric: human.distance
          operator: less_than
          value: 0.5
        action:
          type: block
    """)
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(policy_yaml)

    resp = client.post("/policies/load", json={"path": str(policy_file)})
    assert resp.status_code == 200
    return client


# ---------------------------------------------------------------------------
# Health & root
# ---------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "decisions_in_memory" in data
    assert "active_policies" in data
    assert "trust_sensors" in data


def test_root(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Partenit Analyzer API"
    assert "docs" in data


# ---------------------------------------------------------------------------
# /decisions
# ---------------------------------------------------------------------------


def test_decisions_empty(client: TestClient) -> None:
    resp = client.get("/decisions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_decisions_after_guard_check(client: TestClient) -> None:
    # Create a decision via guard check
    client.post("/guard/check", json={"action": "navigate", "params": {}, "context": {}})
    resp = client.get("/decisions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


def test_decisions_pagination(client: TestClient) -> None:
    # Create two decisions
    for _ in range(3):
        client.post("/guard/check", json={"action": "move", "params": {}, "context": {}})

    resp = client.get("/decisions?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 2


def test_decision_get_by_id(client: TestClient) -> None:
    resp = client.post("/guard/check", json={"action": "navigate", "params": {}, "context": {}})
    packet_id = resp.json()["packet_id"]

    resp2 = client.get(f"/decisions/{packet_id}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["packet_id"] == packet_id
    assert "_verified" in data


def test_decision_get_not_found(client: TestClient) -> None:
    resp = client.get("/decisions/nonexistent-id-xyz")
    assert resp.status_code == 404


def test_decision_verify(client: TestClient) -> None:
    resp = client.post("/guard/check", json={"action": "navigate", "params": {}, "context": {}})
    packet_id = resp.json()["packet_id"]

    resp2 = client.get(f"/decisions/{packet_id}/verify")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["packet_id"] == packet_id
    assert data["verified"] is True
    assert "fingerprint" in data


def test_decision_verify_not_found(client: TestClient) -> None:
    resp = client.get("/decisions/no-such-packet/verify")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /guard/check
# ---------------------------------------------------------------------------


def test_guard_check_no_policies(client: TestClient) -> None:
    """With no policies, guard allows everything."""
    resp = client.post("/guard/check", json={
        "action": "navigate_to",
        "params": {"speed": 1.5, "zone": "A"},
        "context": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "decision" in data
    assert data["decision"]["allowed"] is True


def test_guard_check_with_blocking_policy(client_with_policies: TestClient) -> None:
    """With a blocking policy and human close, guard blocks."""
    resp = client_with_policies.post("/guard/check", json={
        "action": "navigate",
        "params": {},
        "context": {"human": {"distance": 0.3}},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"]["allowed"] is False


def test_guard_check_logs_decision_by_default(client: TestClient) -> None:
    resp = client.post("/guard/check", json={"action": "test", "params": {}, "context": {}})
    assert resp.status_code == 200
    assert "packet_id" in resp.json()
    assert "fingerprint" in resp.json()
    assert "verified" in resp.json()


def test_guard_check_no_log(client: TestClient) -> None:
    resp = client.post("/guard/check", json={
        "action": "test",
        "params": {},
        "context": {},
        "log_decision": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "packet_id" not in data


# ---------------------------------------------------------------------------
# /policies
# ---------------------------------------------------------------------------


def test_policies_active_empty(client: TestClient) -> None:
    resp = client.get("/policies/active")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["rules"] == []


def test_policies_load_valid(client: TestClient, tmp_path) -> None:
    policy_yaml = textwrap.dedent("""\
        rule_id: speed_cap
        name: Speed Cap
        priority: task
        condition:
          type: threshold
          metric: speed
          operator: greater_than
          value: 2.0
        action:
          type: clamp
          parameter: speed
          value: 2.0
    """)
    p = tmp_path / "pol.yaml"
    p.write_text(policy_yaml)
    resp = client.post("/policies/load", json={"path": str(p)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["loaded"] >= 1


def test_policies_load_invalid_path(client: TestClient) -> None:
    resp = client.post("/policies/load", json={"path": "/nonexistent/path/policy.yaml"})
    assert resp.status_code == 400


def test_policies_active_after_load(client: TestClient, tmp_path) -> None:
    policy_yaml = textwrap.dedent("""\
        rule_id: speed_cap
        name: Speed Cap
        priority: task
        condition:
          type: threshold
          metric: speed
          operator: greater_than
          value: 2.0
        action:
          type: clamp
          parameter: speed
          value: 2.0
    """)
    p = tmp_path / "pol.yaml"
    p.write_text(policy_yaml)
    client.post("/policies/load", json={"path": str(p)})

    resp = client.get("/policies/active")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert any(r["rule_id"] == "speed_cap" for r in data["rules"])


# ---------------------------------------------------------------------------
# /trust
# ---------------------------------------------------------------------------


def test_trust_current_empty(client: TestClient) -> None:
    resp = client.get("/trust/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["sensors"] == []


# ---------------------------------------------------------------------------
# /scenarios
# ---------------------------------------------------------------------------

SIMPLE_SCENARIO_YAML = textwrap.dedent("""\
    scenario_id: api_test_scenario
    robot:
      start_position: [0, 0, 0]
      goal_position: [5, 0, 0]
      initial_speed: 1.0
    world:
      humans: []
    policies: []
    expected_events: []
    duration: 5.0
    dt: 0.1
""")

HUMAN_SCENARIO_YAML = textwrap.dedent("""\
    scenario_id: api_human_test
    robot:
      start_position: [0, 0, 0]
      goal_position: [10, 0, 0]
      initial_speed: 1.0
    world:
      humans:
        - id: h1
          start_position: [3, 0.5, 0]
          velocity: [0, 0, 0]
          arrival_time: 0.0
    policies: []
    expected_events: []
    duration: 10.0
    dt: 0.1
""")


def test_scenarios_run_no_guard(client: TestClient) -> None:
    resp = client.post("/scenarios/run", json={
        "scenario_yaml": SIMPLE_SCENARIO_YAML,
        "with_guard": False,
        "seed": 42,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario_id"] == "api_test_scenario"
    assert data["with_guard"] is False
    assert "decisions_total" in data


def test_scenarios_run_with_guard(client: TestClient) -> None:
    resp = client.post("/scenarios/run", json={
        "scenario_yaml": SIMPLE_SCENARIO_YAML,
        "with_guard": True,
        "seed": 42,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["with_guard"] is True


def test_scenarios_run_invalid_yaml(client: TestClient) -> None:
    resp = client.post("/scenarios/run", json={
        "scenario_yaml": "not: valid: yaml: [[[",
        "with_guard": False,
    })
    assert resp.status_code == 400


def test_scenarios_run_no_infinity_in_response(client: TestClient) -> None:
    """min_human_distance_m defaults to inf — must be None (not inf) in JSON."""
    resp = client.post("/scenarios/run", json={
        "scenario_yaml": SIMPLE_SCENARIO_YAML,
        "with_guard": False,
        "seed": 42,
    })
    assert resp.status_code == 200
    # JSON must be valid — if inf leaked, this would have failed already.
    # Additionally, no human means distance = None (was inf, now serialized as null).
    data = resp.json()
    assert data.get("min_human_distance_m") is None  # inf → None


def test_scenarios_run_with_human_has_distance(client: TestClient) -> None:
    """When a human is present, min_human_distance_m must be a finite float."""
    resp = client.post("/scenarios/run", json={
        "scenario_yaml": HUMAN_SCENARIO_YAML,
        "with_guard": False,
        "seed": 42,
    })
    assert resp.status_code == 200
    data = resp.json()
    dist = data.get("min_human_distance_m")
    assert dist is not None
    assert isinstance(dist, float)
    assert dist < 1e6  # finite


def test_scenarios_results_accumulate(client: TestClient) -> None:
    for _ in range(2):
        client.post("/scenarios/run", json={
            "scenario_yaml": SIMPLE_SCENARIO_YAML,
            "with_guard": False,
            "seed": 42,
        })
    resp = client.get("/scenarios/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 2


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------


def test_metrics_endpoint(client: TestClient) -> None:
    resp = client.get("/metrics")
    # Either 200 (prometheus_client installed) or 501 (not installed)
    assert resp.status_code in (200, 501)
    if resp.status_code == 200:
        assert b"partenit_guard" in resp.content
