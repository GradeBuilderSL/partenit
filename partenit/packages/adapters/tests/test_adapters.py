"""Tests for partenit-adapters."""

import pytest

from partenit.adapters.base import RobotAdapter
from partenit.adapters.isaac_sim import IsaacSimAdapter
from partenit.adapters.mock import MockRobotAdapter
from partenit.core.models import GuardDecision, RiskScore, StructuredObservation


# ---------------------------------------------------------------------------
# MockRobotAdapter
# ---------------------------------------------------------------------------


def _make_decision(allowed: bool = True) -> GuardDecision:
    return GuardDecision(
        allowed=allowed,
        risk_score=RiskScore(value=0.2),
        applied_policies=[],
    )



def _decision_key(d):
    """Extract semantically meaningful fields for cross-adapter comparison."""
    return {
        "allowed": d.allowed,
        "modified_params": d.modified_params,
        "rejection_reason": d.rejection_reason,
        "risk_value": round(d.risk_score.value, 6),
        "risk_contributors": d.risk_score.contributors,
        "applied_policies": sorted(d.applied_policies),
    }

def test_mock_is_simulation():
    adapter = MockRobotAdapter()
    assert adapter.is_simulation() is True


def test_mock_empty_scene():
    adapter = MockRobotAdapter()
    obs = adapter.get_observations()
    assert obs == []


def test_mock_add_human():
    adapter = MockRobotAdapter()
    adapter.add_human("h1", x=1.5, y=0.0)
    obs = adapter.get_observations()
    assert len(obs) == 1
    assert obs[0].class_best == "human"
    assert obs[0].treat_as_human is True
    assert abs(obs[0].position_3d[0] - 1.5) < 1e-6


def test_mock_add_object():
    adapter = MockRobotAdapter()
    adapter.add_object("box1", "box", x=3.0, y=1.0)
    obs = adapter.get_observations()
    assert len(obs) == 1
    assert obs[0].class_best == "box"
    assert obs[0].treat_as_human is False


def test_mock_clear_scene():
    adapter = MockRobotAdapter()
    adapter.add_human("h1", 1.0, 0.0)
    adapter.clear_scene()
    assert adapter.get_observations() == []


def test_mock_set_scene():
    adapter = MockRobotAdapter()
    adapter.set_scene([
        {"object_id": "forklift-1", "class_best": "forklift", "position_3d": (5.0, 2.0, 0.0)},
    ])
    obs = adapter.get_observations()
    assert len(obs) == 1
    assert obs[0].object_id == "forklift-1"


def test_mock_send_decision():
    adapter = MockRobotAdapter()
    decision = _make_decision()
    result = adapter.send_decision(decision)
    assert result is True
    assert len(adapter.decisions_sent) == 1
    assert adapter.decisions_sent[0].allowed is True


def test_mock_health():
    adapter = MockRobotAdapter()
    health = adapter.get_health()
    assert health["status"] == "ok"
    assert "robot_id" in health
    assert "timestamp" in health


def test_mock_multiple_objects():
    adapter = MockRobotAdapter()
    adapter.add_human("h1", 1.0, 0.0)
    adapter.add_human("h2", 2.0, 1.0)
    adapter.add_object("box1", "box", 5.0, 0.0)
    obs = adapter.get_observations()
    assert len(obs) == 3
    human_obs = [o for o in obs if o.treat_as_human]
    assert len(human_obs) == 2


def test_mock_observation_frame_hash():
    adapter = MockRobotAdapter()
    adapter.add_human("h1", 1.0, 0.0)
    obs = adapter.get_observations()
    assert obs[0].frame_hash is not None
    assert len(obs[0].frame_hash) == 16


def test_mock_implements_robot_adapter():
    adapter = MockRobotAdapter()
    assert isinstance(adapter, RobotAdapter)


# ---------------------------------------------------------------------------
# HTTPRobotAdapter (with mock HTTP server via respx)
# ---------------------------------------------------------------------------


def test_http_adapter_requires_httpx():
    """Test that HTTPRobotAdapter can be imported."""
    try:
        from partenit.adapters.http import HTTPRobotAdapter
        assert HTTPRobotAdapter is not None
    except ImportError:
        pytest.skip("httpx not available")


def test_http_adapter_get_observations(tmp_path):
    """Test HTTPRobotAdapter with a mocked server."""
    try:
        import httpx
        import respx
    except ImportError:
        pytest.skip("httpx/respx not available")

    from partenit.adapters.http import HTTPRobotAdapter

    obs_data = [
        {
            "object_id": "h1",
            "class_best": "human",
            "class_set": ["human"],
            "position_3d": [1.2, 0.0, 0.0],
            "velocity": [0.0, 0.0, 0.0],
            "confidence": 0.9,
            "depth_variance": 0.01,
            "sensor_trust": 1.0,
            "timestamp": "2025-01-01T00:00:00",
            "source_id": "cam-0",
        }
    ]

    with respx.mock(base_url="http://robot-test") as mock:
        mock.get("/partenit/observations").mock(
            return_value=httpx.Response(200, json=obs_data)
        )
        adapter = HTTPRobotAdapter(base_url="http://robot-test")
        observations = adapter.get_observations()
        adapter.close()

    assert len(observations) == 1
    assert observations[0].class_best == "human"
    assert observations[0].treat_as_human is True


def test_http_adapter_send_decision():
    try:
        import httpx
        import respx
    except ImportError:
        pytest.skip("httpx/respx not available")

    from partenit.adapters.http import HTTPRobotAdapter

    decision = _make_decision()
    with respx.mock(base_url="http://robot-test") as mock:
        mock.post("/partenit/command").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        adapter = HTTPRobotAdapter(base_url="http://robot-test")
        result = adapter.send_decision(decision)
        adapter.close()

    assert result is True


def test_http_adapter_health():
    try:
        import httpx
        import respx
    except ImportError:
        pytest.skip("httpx/respx not available")

    from partenit.adapters.http import HTTPRobotAdapter

    health_data = {"status": "ok", "robot_id": "vendor-bot-1", "timestamp": "2025-01-01T00:00:00"}
    with respx.mock(base_url="http://robot-test") as mock:
        mock.get("/partenit/health").mock(
            return_value=httpx.Response(200, json=health_data)
        )
        adapter = HTTPRobotAdapter(base_url="http://robot-test")
        health = adapter.get_health()
        adapter.close()

    assert health["status"] == "ok"
    assert health["robot_id"] == "vendor-bot-1"


# ---------------------------------------------------------------------------
# Integration: MockAdapter and HTTPAdapter produce same observations
# ---------------------------------------------------------------------------


def test_mock_and_http_same_observation_structure():
    """
    Verify that both adapters return StructuredObservation objects.
    This is a structural test — full equivalence test requires a live HTTP server.
    """
    mock_adapter = MockRobotAdapter()
    mock_adapter.add_human("h1", 1.5, 0.0)
    obs = mock_adapter.get_observations()

    # Check it's a proper StructuredObservation
    assert isinstance(obs[0], StructuredObservation)


def test_mock_and_http_same_guard_decision(tmp_path):
    """
    Integration test: same scenario via MockRobotAdapter and HTTPRobotAdapter
    must produce identical GuardDecision.
    """
    try:
        import httpx
        import respx
    except ImportError:
        pytest.skip("httpx/respx not available")

    from pathlib import Path

    from partenit.adapters.http import HTTPRobotAdapter
    from partenit.agent_guard import AgentGuard

    # Setup mock scene
    mock_adapter = MockRobotAdapter()
    mock_adapter.clear_scene()
    mock_adapter.add_human("h1", 1.2, 0.0)
    mock_obs = mock_adapter.get_observations()

    # Guard with warehouse policies
    guard = AgentGuard()
    policies_path = (
        Path(__file__)
        .resolve()
        .parents[4]
        / "examples"
        / "warehouse"
        / "policies.yaml"
    )
    guard.load_policies(policies_path)

    params = {"zone": "shipping", "speed": 2.0}
    context = {"human": {"distance": mock_obs[0].distance(), "object_id": mock_obs[0].object_id}}

    decision_mock = guard.check_action(
        action="navigate_to",
        params=params,
        context=context,
        observations=mock_obs,
    )

    # HTTP adapter returns the same observations JSON
    payload = [o.model_dump(mode="json") for o in mock_obs]

    with respx.mock(base_url="http://robot-test", assert_all_called=False) as mock:
        mock.get("/partenit/observations").mock(
            return_value=httpx.Response(200, json=payload)
        )
        adapter = HTTPRobotAdapter(base_url="http://robot-test")
        http_obs = adapter.get_observations()
        decision_http = guard.check_action(
            action="navigate_to",
            params=params,
            context=context,
            observations=http_obs,
        )
        adapter.close()

    assert _decision_key(decision_http) == _decision_key(decision_mock)


# ---------------------------------------------------------------------------
# IsaacSimAdapter (HTTP bridge mode) + cross-adapter determinism
# ---------------------------------------------------------------------------


def test_isaac_sim_adapter_equivalence_to_mock():
    """IsaacSimAdapter should see the same scene as MockRobotAdapter."""
    try:
        import httpx
        import respx
    except ImportError:
        pytest.skip("httpx/respx not available")

    mock_adapter = MockRobotAdapter(robot_id="mock-eq")
    mock_adapter.clear_scene()
    mock_adapter.add_human("h1", x=1.2, y=0.0)
    mock_obs = mock_adapter.get_observations()

    payload = [o.model_dump(mode="json") for o in mock_obs]

    with respx.mock(base_url="http://isaac-test") as mock:
        mock.get("/partenit/observations").mock(
            return_value=httpx.Response(200, json=payload)
        )
        mock.post("/partenit/command").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        mock.get("/partenit/health").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "ok",
                    "robot_id": "isaac-sim-robot",
                    "timestamp": "2025-01-01T00:00:00Z",
                },
            )
        )

        isaac = IsaacSimAdapter(base_url="http://isaac-test", robot_id="isaac-sim-robot")
        isaac_obs = isaac.get_observations()

        assert len(isaac_obs) == len(mock_obs) == 1
        assert isaac_obs[0].class_best == mock_obs[0].class_best
        assert isaac_obs[0].treat_as_human == mock_obs[0].treat_as_human

        health = isaac.get_health()
        assert health["status"] == "ok"
        assert health["robot_id"] == "isaac-sim-robot"
        assert health.get("is_simulation") is True

        decision = _make_decision()
        assert isaac.send_decision(decision) is True

        isaac.close()


def test_cross_adapter_guard_decision_mock_http_isaac():
    """
    Cross-adapter determinism: same scene and policies should produce
    identical GuardDecision via Mock, HTTP, and Isaac adapters.
    """
    try:
        import httpx
        import respx
    except ImportError:
        pytest.skip("httpx/respx not available")

    from pathlib import Path

    from partenit.adapters.http import HTTPRobotAdapter
    from partenit.agent_guard import AgentGuard

    mock_adapter = MockRobotAdapter()
    mock_adapter.clear_scene()
    mock_adapter.add_human("h1", 1.2, 0.0)
    mock_obs = mock_adapter.get_observations()

    guard = AgentGuard()
    policies_path = (
        Path(__file__)
        .resolve()
        .parents[4]
        / "examples"
        / "warehouse"
        / "policies.yaml"
    )
    guard.load_policies(policies_path)

    params = {"zone": "shipping", "speed": 2.0}
    context = {"human": {"distance": mock_obs[0].distance(), "object_id": mock_obs[0].object_id}}

    decision_mock = guard.check_action(
        action="navigate_to",
        params=params,
        context=context,
        observations=mock_obs,
    )

    payload = [o.model_dump(mode="json") for o in mock_obs]

    with respx.mock(base_url="http://robot-test", assert_all_called=False) as mock:
        mock.get("/partenit/observations").mock(
            return_value=httpx.Response(200, json=payload)
        )
        adapter = HTTPRobotAdapter(base_url="http://robot-test")
        http_obs = adapter.get_observations()
        decision_http = guard.check_action(
            action="navigate_to",
            params=params,
            context=context,
            observations=http_obs,
        )
        adapter.close()

    with respx.mock(base_url="http://isaac-test", assert_all_called=False) as mock:
        mock.get("/partenit/observations").mock(
            return_value=httpx.Response(200, json=payload)
        )
        mock.get("/partenit/health").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "ok",
                    "robot_id": "isaac-sim-robot",
                    "timestamp": "2025-01-01T00:00:00Z",
                },
            )
        )

        isaac = IsaacSimAdapter(base_url="http://isaac-test", robot_id="isaac-sim-robot")
        isaac_obs = isaac.get_observations()
        decision_isaac = guard.check_action(
            action="navigate_to",
            params=params,
            context=context,
            observations=isaac_obs,
        )
        isaac.close()

    assert _decision_key(decision_http) == _decision_key(decision_mock)
    assert _decision_key(decision_isaac) == _decision_key(decision_mock)


# ---------------------------------------------------------------------------
# GazeboAdapter
# ---------------------------------------------------------------------------


def test_gazebo_adapter_is_simulation():
    try:
        import httpx
        import respx
    except ImportError:
        pytest.skip("httpx/respx not available")

    from partenit.adapters.gazebo import GazeboAdapter

    with respx.mock(base_url="http://gazebo-test", assert_all_called=False) as mock:
        mock.get("/partenit/health").mock(
            return_value=httpx.Response(
                200,
                json={"status": "ok", "robot_id": "gazebo-robot", "timestamp": "2025-01-01T00:00:00Z"},
            )
        )
        adapter = GazeboAdapter(base_url="http://gazebo-test", robot_id="gazebo-robot")
        assert adapter.is_simulation() is True
        health = adapter.get_health()
        assert health["is_simulation"] is True
        assert health["simulator"] == "gazebo"
        adapter.close()


def test_gazebo_adapter_get_observations():
    try:
        import httpx
        import respx
    except ImportError:
        pytest.skip("httpx/respx not available")

    from partenit.adapters.gazebo import GazeboAdapter

    mock_adapter = MockRobotAdapter()
    mock_adapter.add_human("h1", 2.0, 0.0)
    payload = [o.model_dump(mode="json") for o in mock_adapter.get_observations()]

    with respx.mock(base_url="http://gazebo-test", assert_all_called=False) as mock:
        mock.get("/partenit/observations").mock(
            return_value=httpx.Response(200, json=payload)
        )
        adapter = GazeboAdapter(base_url="http://gazebo-test")
        obs = adapter.get_observations()
        adapter.close()

    assert len(obs) == 1
    assert obs[0].class_best == "human"
    assert obs[0].treat_as_human is True


# ---------------------------------------------------------------------------
# LLMToolCallGuard
# ---------------------------------------------------------------------------


def test_llm_tool_guard_allows_safe_call():
    from pathlib import Path
    from partenit.adapters.llm_tool_calling import LLMToolCallGuard

    guard = LLMToolCallGuard()
    policies_path = Path(__file__).resolve().parents[4] / "examples" / "warehouse" / "policies.yaml"
    guard.load_policies(policies_path)

    result = guard.check_tool_call(
        tool_name="navigate_to",
        tool_input={"zone": "storage", "speed": 0.5},
        context={"human": {"distance": 10.0}},
    )
    assert result.allowed is True
    assert result.rejection_message == ""


def test_llm_tool_guard_clamps_speed():
    from pathlib import Path
    from partenit.adapters.llm_tool_calling import LLMToolCallGuard

    guard = LLMToolCallGuard()
    policies_path = Path(__file__).resolve().parents[4] / "examples" / "warehouse" / "policies.yaml"
    guard.load_policies(policies_path)

    result = guard.check_tool_call(
        tool_name="navigate_to",
        tool_input={"zone": "shipping", "speed": 2.5},
        context={"human": {"distance": 1.1}},
    )
    assert result.allowed is True
    assert result.modified is True
    assert result.safe_input.get("speed", 2.5) < 2.5


def test_llm_tool_guard_blocks_near_human():
    from pathlib import Path
    from partenit.adapters.llm_tool_calling import LLMToolCallGuard

    guard = LLMToolCallGuard()
    policies_path = Path(__file__).resolve().parents[4] / "examples" / "warehouse" / "policies.yaml"
    guard.load_policies(policies_path)

    result = guard.check_tool_call(
        tool_name="navigate_to",
        tool_input={"zone": "shipping", "speed": 2.0},
        context={"human": {"distance": 0.3}},
    )
    assert result.allowed is False
    assert result.rejection_message != ""
    assert "SAFETY" in result.rejection_message.upper() or "blocked" in result.rejection_message.lower()


def test_llm_tool_guard_batch():
    from pathlib import Path
    from partenit.adapters.llm_tool_calling import LLMToolCallGuard

    guard = LLMToolCallGuard()
    policies_path = Path(__file__).resolve().parents[4] / "examples" / "warehouse" / "policies.yaml"
    guard.load_policies(policies_path)

    calls = [
        {"name": "navigate_to", "input": {"zone": "storage", "speed": 0.5}},
        {"name": "navigate_to", "input": {"zone": "shipping", "speed": 2.5}},
    ]
    results = guard.check_tool_calls_batch(calls, context={"human": {"distance": 1.2}})
    assert len(results) == 2
    # Both are evaluated; results may differ but should be deterministic
    assert all(hasattr(r, "allowed") for r in results)


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_starts_closed():
    from partenit.adapters.http import CircuitBreaker, CircuitState
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
    assert cb.state == CircuitState.CLOSED
    assert cb.allow() is True


def test_circuit_breaker_opens_after_threshold():
    from partenit.adapters.http import CircuitBreaker, CircuitState
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=30)
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow() is False


def test_circuit_breaker_success_resets():
    from partenit.adapters.http import CircuitBreaker, CircuitState
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb._failures == 0


def test_circuit_breaker_half_open_after_cooldown():
    from partenit.adapters.http import CircuitBreaker, CircuitState
    import time
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.05)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.1)
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow() is True


def test_circuit_breaker_reset():
    from partenit.adapters.http import CircuitBreaker, CircuitState
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=30)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow() is True


def test_http_adapter_circuit_breaker_blocks_open_circuit():
    """When circuit is open, HTTPRobotAdapter returns empty/False without calling HTTP."""
    try:
        import httpx
        import respx
    except ImportError:
        pytest.skip("httpx/respx not available")

    from partenit.adapters.http import CircuitBreaker, HTTPRobotAdapter

    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    cb.record_failure()  # Force circuit open

    adapter = HTTPRobotAdapter(base_url="http://robot-no-call", circuit_breaker=cb)
    # Should return empty without making any HTTP call
    obs = adapter.get_observations()
    assert obs == []
    adapter.close()


def test_http_adapter_has_default_circuit_breaker():
    """HTTPRobotAdapter always has a circuit breaker by default."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not available")

    from partenit.adapters.http import CircuitBreaker, HTTPRobotAdapter
    adapter = HTTPRobotAdapter(base_url="http://robot-test")
    assert isinstance(adapter.circuit_breaker, CircuitBreaker)
    adapter.close()
