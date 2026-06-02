"""Integration tests for /api/v1/statistics/session/{session_id} - B2 Session Analytics.

Tests the complete flow: backend API -> EventLogger -> EventLog files -> frontend.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_session_analytics_endpoint_with_real_session():
    """Test /api/v1/statistics/session/{session_id} with a real session."""
    # Use httpx to call the API
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # First, check if there are any sessions
        response = await ac.get(
            "/api/v1/statistics/usage/sessions", params={"limit": 1}
        )
        assert response.status_code == 200

        data = response.json()
        sessions = data.get("data", {}).get("sessions", [])

        if not sessions:
            pytest.skip("No sessions available for testing")

        # Get the first session
        session_id = sessions[0]["chatId"]

        # Now call the session analytics endpoint
        response = await ac.get(f"/api/v1/statistics/session/{session_id}")

        # Assertions
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert "data" in result

        analytics = result["data"]
        assert "session_id" in analytics
        assert "duration_ms" in analytics
        assert "tool_breakdown" in analytics
        assert "events_timeline" in analytics
        assert "task_metrics" in analytics
        assert "context_health" in analytics
        assert isinstance(analytics["tool_breakdown"], list)
        assert isinstance(analytics["events_timeline"], list)


@pytest.mark.asyncio
async def test_session_analytics_endpoint_not_found():
    """Test /api/v1/statistics/session/{session_id} with non-existent session."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/statistics/session/non-existent-session-id")

        # Should return 404 or empty data
        assert response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_session_analytics_endpoint_structure():
    """Test session analytics response structure."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Get a session
        response = await ac.get(
            "/api/v1/statistics/usage/sessions", params={"limit": 1}
        )
        if response.status_code != 200:
            pytest.skip("Cannot fetch sessions")

        sessions = response.json().get("data", {}).get("sessions", [])
        if not sessions:
            pytest.skip("No sessions available")

        session_id = sessions[0]["chatId"]

        # Get session analytics
        response = await ac.get(f"/api/v1/statistics/session/{session_id}")
        assert response.status_code == 200

        analytics = response.json()["data"]

        # Verify structure
        assert isinstance(analytics["session_id"], str)
        assert isinstance(analytics["duration_ms"], (int, float))
        assert isinstance(analytics["tool_breakdown"], list)
        assert isinstance(analytics["context_health"], dict)

        # Verify tool_breakdown structure if present
        if analytics["tool_breakdown"]:
            tool = analytics["tool_breakdown"][0]
            assert "tool_name" in tool
            assert "call_count" in tool
            assert "total_duration_ms" in tool

        # Verify events_timeline structure if present
        if analytics["events_timeline"]:
            event = analytics["events_timeline"][0]
            assert "type" in event
            assert "timestamp" in event
            assert "data" in event


@pytest.mark.asyncio
async def test_session_trace_endpoint_with_real_session():
    """Test /api/v1/statistics/session/{session_id}/trace with a real session."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(
            "/api/v1/statistics/usage/sessions", params={"limit": 1}
        )
        assert response.status_code == 200

        sessions = response.json().get("data", {}).get("sessions", [])
        if not sessions:
            pytest.skip("No sessions available for testing")

        session_id = sessions[0]["chatId"]
        response = await ac.get(f"/api/v1/statistics/session/{session_id}/trace")

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True

        trace = result["data"]
        assert "session_id" in trace
        assert "metadata" in trace
        assert "outcome" in trace
        assert "tool_calls" in trace
        assert "errors" in trace
        assert "human_feedback" in trace
        assert "memory_events" in trace
        assert isinstance(trace["tool_calls"], list)
        assert isinstance(trace["errors"], list)
        assert isinstance(trace["memory_events"], list)
        assert trace["outcome"] in ("success", "failure", "cancelled", "unknown")


@pytest.mark.asyncio
async def test_session_trace_endpoint_not_found():
    """Test /api/v1/statistics/session/{session_id}/trace with non-existent session."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/statistics/session/non-existent-id/trace")
        assert response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_session_trace_endpoint_structure():
    """Test trace response structure has all expected fields."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(
            "/api/v1/statistics/usage/sessions", params={"limit": 1}
        )
        if response.status_code != 200:
            pytest.skip("Cannot fetch sessions")

        sessions = response.json().get("data", {}).get("sessions", [])
        if not sessions:
            pytest.skip("No sessions available")

        session_id = sessions[0]["chatId"]
        response = await ac.get(f"/api/v1/statistics/session/{session_id}/trace")
        assert response.status_code == 200

        trace = response.json()["data"]

        assert isinstance(trace["session_id"], str)
        assert isinstance(trace["metadata"], dict)
        assert isinstance(trace["start_time"], (int, float))
        assert isinstance(trace["end_time"], (int, float))
        assert isinstance(trace["duration_ms"], (int, float))
        assert isinstance(trace["total_events"], int)
        assert isinstance(trace["total_tokens"], int)
        assert isinstance(trace["memory_events"], list)

        if trace["tool_calls"]:
            tc = trace["tool_calls"][0]
            assert "sequence" in tc
            assert "tool_name" in tc
            assert "start_time" in tc
            assert "success" in tc


@pytest.mark.asyncio
async def test_model_sessions_endpoint_basic():
    """Test /api/v1/statistics/usage/model-sessions with mock or non-existent model."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Query with a non-existent/dummy model name
        response = await ac.get(
            "/api/v1/statistics/usage/model-sessions",
            params={"model": "nonexistent-provider/nonexistent-model", "days": 30},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert "data" in result
        assert isinstance(result["data"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
