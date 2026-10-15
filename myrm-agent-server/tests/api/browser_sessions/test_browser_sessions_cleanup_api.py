"""The saved-sessions cleanup endpoint clears expired sessions from the global vault and every agent vault."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.core.security.browser_vault as vault_module
from app.api.browser_sessions.router import router


@pytest.fixture(autouse=True)
def _real_vaults_in_tmp_state_dir(tmp_path: Path) -> Iterator[None]:
    """Real encrypted file vaults rooted in a temporary state directory."""
    settings = MagicMock()
    settings.database.state_dir = str(tmp_path)
    vault_module._global_vault = None
    vault_module._agent_vaults.clear()
    with patch("app.config.settings.settings", settings):
        yield
    vault_module._global_vault = None
    vault_module._agent_vaults.clear()


@pytest.mark.asyncio
async def test_cleanup_removes_expired_sessions_of_the_global_vault_and_every_agent_vault() -> None:
    global_vault = vault_module.get_global_session_vault()
    agent_vault = vault_module.get_agent_session_vault("agent_a")
    await global_vault.save("global-expired.test", {"cookies": []}, ttl_days=-1)
    await global_vault.save("global-live.test", {"cookies": []})
    await agent_vault.save("agent-expired.test", {"cookies": []}, ttl_days=-1)
    await agent_vault.save("agent-live.test", {"cookies": []})

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/browser")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/browser/sessions/cleanup")

    assert response.status_code == 200
    assert response.json() == {"removed": 2}
    assert set(await global_vault.list_domains()) == {"global-live.test"}
    assert set(await agent_vault.list_domains()) == {"agent-live.test"}
