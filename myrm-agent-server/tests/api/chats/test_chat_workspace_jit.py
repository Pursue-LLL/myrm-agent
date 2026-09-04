"""GET /chats/{id} JIT-binds harness workspace_dir when DB value is unset."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")
from app.services.chat.chat_service import ChatService
from app.services.agent.params.workspace_resolve import _materialize_agent_template_files


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_chat_populates_workspace_dir_when_null(
    async_client: httpx.AsyncClient,
) -> None:
    """[evidence] Mirrors agent_params converter: chat_{{id}} sandbox path exposed to frontend."""
    chat_id = f"test-ws-jit-{uuid.uuid4().hex[:8]}"

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(
            id=chat_id,
            title="JIT workspace probe",
            action_mode="agent",
            source="web",
        )
        db.add(chat)
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}")
    assert res.status_code == 200, res.text
    payload = res.json()
    ws = payload["data"]["chat"]["workspace_dir"]
    assert isinstance(ws, str) and len(ws) > 0

    meta = await ChatService.get_chat_metadata(chat_id)
    assert meta is not None
    assert meta.workspace_dir == ws


@pytest.mark.asyncio
async def test_get_chat_preserves_existing_workspace_dir(
    async_client: httpx.AsyncClient,
) -> None:
    """If DB already has workspace_dir, GET must not overwrite with a different string."""
    chat_id = f"test-ws-keep-{uuid.uuid4().hex[:8]}"
    existing = "/tmp/myrm_workspace_jit_should_not_exist_please"

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(
            id=chat_id,
            title="Keep workspace_dir",
            action_mode="agent",
            source="web",
            workspace_dir=existing,
        )
        db.add(chat)
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}")
    assert res.status_code == 200, res.text
    assert res.json()["data"]["chat"]["workspace_dir"] == existing


@pytest.mark.asyncio
async def test_materialize_agent_template_files_security_and_writing(tmp_path: Path) -> None:
    """Verifies that _materialize_agent_template_files writes text/base64 files and blocks path traversal."""
    import base64
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.services.agent.params.workspace_resolve import _materialize_agent_template_files

    chat_id = "test-chat-materialize-1"
    target_workspace = tmp_path / "sandbox_ws"
    target_workspace.mkdir(parents=True, exist_ok=True)

    # Pre-existing file should not be overwritten
    (target_workspace / "existing.txt").write_text("initial content", encoding="utf-8")

    mock_chat = SimpleNamespace(agent_id="test-agent-with-templates")
    b64_data = base64.b64encode(b"binary asset data").decode("utf-8")
    mock_profile = SimpleNamespace(
        engine_params={
            "template_workspace_files": {
                "templates/report.md": "# Research Report Template",
                "assets/logo.png": f"base64:{b64_data}",
                "existing.txt": "overwritten content should not happen",
                "../escape.txt": "malicious content",
            }
        }
    )

    mock_resolver = SimpleNamespace(
        resolve=AsyncMock(return_value=mock_profile)
    )

    with (
        patch("app.services.chat.chat_service.ChatService.get_chat_metadata", AsyncMock(return_value=mock_chat)),
        patch("app.services.agent.profile.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
    ):
        await _materialize_agent_template_files(chat_id, str(target_workspace))

    # 1. Normal text file written
    report_file = target_workspace / "templates" / "report.md"
    assert report_file.exists()
    assert report_file.read_text(encoding="utf-8") == "# Research Report Template"

    # 2. Base64 decoded binary file written
    logo_file = target_workspace / "assets" / "logo.png"
    assert logo_file.exists()
    assert logo_file.read_bytes() == b"binary asset data"

    # 3. Existing file preserved
    existing_file = target_workspace / "existing.txt"
    assert existing_file.read_text(encoding="utf-8") == "initial content"

    # 4. Path traversal blocked
    escape_file = tmp_path / "escape.txt"
    assert not escape_file.exists()


@pytest.mark.asyncio
async def test_materialize_agent_template_files_from_metadata(tmp_path: Path) -> None:
    """Verifies that engine_params stored inside profile.metadata is correctly unpacked."""
    target_workspace = tmp_path / "workspace_meta"
    target_workspace.mkdir(parents=True, exist_ok=True)
    chat_id = "test-chat-meta"

    mock_chat = SimpleNamespace(agent_id="test-agent-meta")
    mock_profile = SimpleNamespace(
        metadata={
            "engine_params": {
                "template_workspace_files": {
                    "docs/readme.txt": "Metadata Readme Content",
                }
            }
        }
    )

    mock_resolver = SimpleNamespace(
        resolve=AsyncMock(return_value=mock_profile)
    )

    with (
        patch("app.services.chat.chat_service.ChatService.get_chat_metadata", AsyncMock(return_value=mock_chat)),
        patch("app.services.agent.profile.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
    ):
        await _materialize_agent_template_files(chat_id, str(target_workspace))

    readme_file = target_workspace / "docs" / "readme.txt"
    assert readme_file.exists()
    assert readme_file.read_text(encoding="utf-8") == "Metadata Readme Content"

