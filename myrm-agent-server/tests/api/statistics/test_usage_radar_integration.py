"""Integration tests for /api/v1/statistics/usage/radar - BYOK Usage Radar Analytics.

Tests the newly implemented O(1) usage radar endpoint to ensure it correctly
returns total_calls, total_tokens, and total_usd from the Chat table.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.database.connection import get_session
from app.database.models.chat import Chat
from app.main import app


@pytest.fixture
async def setup_test_chat_usage():
    """Setup some dummy usage data in the Chat table for testing."""
    async with get_session() as db:
        # Add some usage to an existing chat or create a dummy one
        # For simplicity, we just find the first chat and give it some usage
        result = await db.execute(select(Chat).limit(1))
        chat = result.scalar_one_or_none()

        if chat:
            original_calls = chat.total_calls
            original_tokens = chat.total_tokens
            original_usd = chat.total_usd

            # Update with test data
            await db.execute(
                update(Chat)
                .where(Chat.id == chat.id)
                .values(total_calls=original_calls + 5, total_tokens=original_tokens + 1000, total_usd=original_usd + 0.05)
            )
            await db.commit()

            yield chat.id, original_calls, original_tokens, original_usd

            # Cleanup (restore original data)
            async with get_session() as restore_db:
                await restore_db.execute(
                    update(Chat)
                    .where(Chat.id == chat.id)
                    .values(total_calls=original_calls, total_tokens=original_tokens, total_usd=original_usd)
                )
                await restore_db.commit()
        else:
            yield None, 0, 0, 0.0


@pytest.mark.asyncio
async def test_usage_radar_endpoint_structure():
    """Test the structure and success of the /api/v1/statistics/usage/radar endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/statistics/usage/radar")

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert "data" in result

        data = result["data"]
        # Verify BYOK Usage Radar specific fields
        assert "total_calls" in data
        assert "total_tokens" in data
        assert "total_usd" in data

        assert isinstance(data["total_calls"], int)
        assert isinstance(data["total_tokens"], int)
        assert isinstance(data["total_usd"], (int, float))


@pytest.mark.asyncio
async def test_usage_radar_endpoint_values(setup_test_chat_usage):
    """Test that the radar endpoint correctly sums up the Chat table usage columns."""
    chat_id, orig_calls, orig_tokens, orig_usd = setup_test_chat_usage

    if not chat_id:
        pytest.skip("No chat available in database to test radar values")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/statistics/usage/radar")
        assert response.status_code == 200

        data = response.json()["data"]

        # We know we added 5 calls, 1000 tokens, and 0.05 USD.
        # Since it's a global SUM, it should be at least those values.
        assert data["total_calls"] >= 5
        assert data["total_tokens"] >= 1000
        assert data["total_usd"] >= 0.05


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
