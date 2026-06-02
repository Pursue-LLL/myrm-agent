"""E2E Integration test for Subagent GUI configuration.

Tests that ephemeralSubagents configuration is correctly accepted and parsed
by the backend API without errors.
"""

import json
import os

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.asyncio
class TestSubagentGUIConfigE2E:
    """Test Subagent GUI configuration end-to-end."""

    async def test_ephemeral_subagent_config_accepted(self, async_client: AsyncClient):
        """Test ephemeral subagent configuration is accepted without errors."""
        if not os.getenv("BASIC_API_KEY"):
            pytest.skip("BASIC_API_KEY not configured")

        # Simulate frontend payload with ephemeralSubagents
        payload = {
            "messageId": "test-message-id-1",
            "query": "Hello, please respond.",
            "ephemeralSubagents": {
                "researcher": {
                    "display_name": "@GuiResearcher",
                    "theme_color": "blue",
                    "system_prompt": "You are a research assistant.",
                }
            },
        }

        # Stream response
        async with async_client.stream(
            "POST", "/api/v1/agents/agent-stream", json=payload, timeout=60.0
        ) as response:
            assert (
                response.status_code == 200
            ), f"Expected 200, got {response.status_code}"

            error_found = False

            async for line in response.aiter_lines():
                if not line.strip() or not line.startswith("data:"):
                    continue

                try:
                    data = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue

                # Check for errors
                if data.get("event_type") == "ERROR":
                    error_found = True
                    pytest.fail(f"Unexpected error in stream: {data}")

            # Verify no errors occurred
            assert not error_found, "Errors occurred during streaming"

    async def test_multiple_ephemeral_subagents_accepted(
        self, async_client: AsyncClient
    ):
        """Test multiple ephemeral subagents are accepted without errors."""
        if not os.getenv("BASIC_API_KEY"):
            pytest.skip("BASIC_API_KEY not configured")

        payload = {
            "messageId": "test-message-id-2",
            "query": "Hello, please respond.",
            "ephemeralSubagents": {
                "researcher": {
                    "display_name": "@Researcher",
                    "theme_color": "blue",
                    "system_prompt": "You are a researcher.",
                },
                "coder": {
                    "display_name": "@Coder",
                    "theme_color": "green",
                    "system_prompt": "You are a coder.",
                },
            },
        }

        async with async_client.stream(
            "POST", "/api/v1/agents/agent-stream", json=payload, timeout=60.0
        ) as response:
            assert response.status_code == 200

            async for line in response.aiter_lines():
                if not line.strip() or not line.startswith("data:"):
                    continue

                try:
                    data = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue

                if data.get("event_type") == "ERROR":
                    pytest.fail(f"Unexpected error: {data}")

    async def test_ephemeral_subagent_missing_display_name_accepted(
        self, async_client: AsyncClient
    ):
        """Test ephemeral subagent without display_name is accepted (uses default)."""
        if not os.getenv("BASIC_API_KEY"):
            pytest.skip("BASIC_API_KEY not configured")

        payload = {
            "messageId": "test-message-id-3",
            "query": "Hello, please respond.",
            "ephemeralSubagents": {
                "analyst": {
                    # display_name intentionally omitted
                    "theme_color": "orange",
                    "system_prompt": "You are an analyst.",
                }
            },
        }

        async with async_client.stream(
            "POST", "/api/v1/agents/agent-stream", json=payload, timeout=60.0
        ) as response:
            assert response.status_code == 200

            async for line in response.aiter_lines():
                if not line.strip() or not line.startswith("data:"):
                    continue

                try:
                    data = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue

                if data.get("event_type") == "ERROR":
                    pytest.fail(f"Unexpected error: {data}")

    async def test_ephemeral_subagent_empty_theme_color_accepted(
        self, async_client: AsyncClient
    ):
        """Test ephemeral subagent with empty theme_color is accepted."""
        if not os.getenv("BASIC_API_KEY"):
            pytest.skip("BASIC_API_KEY not configured")

        payload = {
            "messageId": "test-message-id-4",
            "query": "Hello, please respond.",
            "ephemeralSubagents": {
                "reviewer": {
                    "display_name": "@Reviewer",
                    "theme_color": "",  # Empty string
                    "system_prompt": "You are a reviewer.",
                }
            },
        }

        async with async_client.stream(
            "POST", "/api/v1/agents/agent-stream", json=payload, timeout=60.0
        ) as response:
            assert response.status_code == 200

            # Empty theme_color should be accepted without error
            async for line in response.aiter_lines():
                if not line.strip() or not line.startswith("data:"):
                    continue

                try:
                    data = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue

                if data.get("event_type") == "ERROR":
                    pytest.fail(f"Unexpected error: {data}")
