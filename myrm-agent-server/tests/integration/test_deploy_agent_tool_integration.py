"""Integration: deploy_artifact tool wired to real AgentDeployService backend."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.artifacts.listener import upsert_processor_artifact
from app.database.models import Base
from app.services.deploy.agent_deploy_service import AgentDeployService
from app.services.deploy.deploy_agent_tools import create_deploy_tool


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    db_id = uuid.uuid4().hex
    engine = create_async_engine(
        f"sqlite+aiosqlite:///file:deploy_tool_int_{db_id}?mode=memory&cache=shared&uri=true"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _seed_html_artifact(db: AsyncSession, workspace) -> str:
    art_id = str(uuid.uuid4())
    html_path = workspace / "index.html"
    html_path.write_text("<html><body>tool integration</body></html>", encoding="utf-8")
    await upsert_processor_artifact(
        db,
        file_id=art_id,
        filename="index.html",
        sandbox_path=str(html_path),
        workspace_root=str(workspace),
        chat_id=f"chat-{art_id[:8]}",
    )
    return art_id


class TestDeployToolRealBackendIntegration:
    @pytest.mark.asyncio
    async def test_preflight_failure_with_real_backend(self, db_session: AsyncSession, tmp_path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        backend = AgentDeployService(workspace_root=str(workspace))

        @asynccontextmanager
        async def session_override():
            yield db_session

        with patch("app.database.connection.get_session", session_override):
            tool = create_deploy_tool(backend)[0]
            result = await tool.ainvoke({"artifact_id": str(uuid.uuid4())})

        assert "Cannot deploy" in result

    @pytest.mark.asyncio
    async def test_successful_deploy_with_real_backend(self, db_session: AsyncSession, tmp_path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        art_id = await _seed_html_artifact(db_session, workspace)
        backend = AgentDeployService(workspace_root=str(workspace))

        @asynccontextmanager
        async def session_override():
            yield db_session

        with (
            patch("app.database.connection.get_session", session_override),
            patch("app.services.deploy.vercel_client.VercelClient") as mock_vercel_class,
            patch("langgraph.types.interrupt") as mock_interrupt,
        ):
            from app.services.deploy.credentials import save_vercel_credentials

            await save_vercel_credentials(db_session, "tool-backend-token")
            mock_vercel = mock_vercel_class.return_value
            mock_vercel.deploy = AsyncMock(
                return_value={
                    "deployment_id": "dpl_tool",
                    "url": "https://tool-backend.vercel.app",
                    "project_id": "prj_tool",
                    "status": "READY",
                }
            )
            mock_interrupt.return_value = {"decision": "approve"}

            tool = create_deploy_tool(backend)[0]
            result = await tool.ainvoke({"artifact_id": art_id})

        assert "https://tool-backend.vercel.app" in result
        assert mock_interrupt.call_args[0][0]["action_type"] == "deploy_approval"
        mock_vercel_class.assert_called_once_with(token="tool-backend-token")
