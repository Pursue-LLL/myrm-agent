"""GET /skills/{id}/agent-usage counts agent bindings."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app


@pytest.mark.asyncio
async def test_skill_agent_usage_unknown_skill_404() -> None:
    app = build_minimal_app(preset="skills_api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/skills/no-such-skill/agent-usage")
    assert resp.status_code == 404
