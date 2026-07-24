"""Integration tests: evicted API reads UECD spill files."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from myrm_agent_harness.agent.context_management.infra.evicted_content import (
    EVICTED_BASENAME_PATTERN,
    write_evicted_content_sync,
)
from myrm_agent_harness.core.context_vars import chat_id_var, workspace_root_var


def test_server_filename_pattern_matches_harness_ssot() -> None:
    from app.api.files.evicted import _FILENAME_PATTERN

    assert _FILENAME_PATTERN.pattern == EVICTED_BASENAME_PATTERN.pattern


@pytest.mark.asyncio
async def test_read_evicted_web_fetch_md_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = "chat_web_fetch_spill"
    filename = f"web_fetch_{uuid.uuid4().hex[:8]}.md"
    evicted_dir = tmp_path / ".context" / chat_id / "evicted"
    evicted_dir.mkdir(parents=True)
    content = "# Title\n\n" + ("paragraph\n" * 50)
    (evicted_dir / filename).write_text(content, encoding="utf-8")

    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from app.api.files.evicted import router as evicted_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": chat_id, "filename": filename, "offset": 0, "limit": 10},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "Title" in data["content"]


@pytest.mark.asyncio
async def test_read_evicted_limit_zero_returns_full_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = "chat_full_read"
    filename = f"tool_{uuid.uuid4().hex[:8]}.txt"
    evicted_dir = tmp_path / ".context" / chat_id / "evicted"
    evicted_dir.mkdir(parents=True)
    content = "line\n" * 6000
    (evicted_dir / filename).write_text(content, encoding="utf-8")

    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from app.api.files.evicted import router as evicted_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": chat_id, "filename": filename, "offset": 0, "limit": 0},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == content
    assert data["total_lines"] >= 6000


@pytest.mark.asyncio
async def test_uecd_persist_then_api_read_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = "chat_roundtrip"
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))
    w_tok = workspace_root_var.set(str(tmp_path))
    c_tok = chat_id_var.set(chat_id)
    try:
        body = "payload\n" * 8000
        result = write_evicted_content_sync(body, "web_fetch", ext="md")
        assert result.evicted_ref is not None

        from app.api.files.evicted import router as evicted_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(evicted_router, prefix="/api/v1/files")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/files/evicted",
                params={
                    "chat_id": chat_id,
                    "filename": result.evicted_ref,
                    "offset": 0,
                    "limit": 0,
                },
            )

        assert resp.status_code == 200
        assert resp.json()["content"] == body
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)


@pytest.mark.asyncio
async def test_read_evicted_rejects_invalid_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from app.api.files.evicted import router as evicted_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": "chat1", "filename": "../../../etc/passwd"},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_read_evicted_rejects_invalid_chat_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))
    filename = f"output_{uuid.uuid4().hex[:8]}.txt"

    from app.api.files.evicted import router as evicted_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": "../bad", "filename": filename},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_read_evicted_missing_file_returns_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))
    filename = f"output_{uuid.uuid4().hex[:8]}.txt"

    from app.api.files.evicted import router as evicted_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": "chat_missing", "filename": filename},
        )

    assert resp.status_code == 404
    assert resp.json()["detail"]["expired"] is True


@pytest.mark.asyncio
async def test_read_evicted_workspace_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MYRM_WORKSPACE_ROOT", raising=False)
    filename = f"output_{uuid.uuid4().hex[:8]}.txt"

    from app.api.files import evicted as evicted_module
    from app.api.files.evicted import router as evicted_router
    from fastapi import FastAPI

    monkeypatch.setattr(evicted_module, "_get_workspace_root", lambda: None)

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": "chat1", "filename": filename},
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_read_evicted_dangerous_path_returns_403(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = "chat_danger"
    filename = f"output_{uuid.uuid4().hex[:8]}.txt"
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from app.api.files.evicted import router as evicted_router
    from fastapi import FastAPI

    monkeypatch.setattr(
        "myrm_agent_harness.agent.security.path_security.is_dangerous_path",
        lambda _p: True,
    )

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": chat_id, "filename": filename},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_read_evicted_path_traversal_returns_403(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = "chat_escape"
    filename = f"output_{uuid.uuid4().hex[:8]}.txt"
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from app.api.files.evicted import router as evicted_router
    from fastapi import FastAPI

    evicted_dir = tmp_path / ".context" / chat_id / "evicted"
    evicted_dir.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (evicted_dir / filename).symlink_to(outside)

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": chat_id, "filename": filename},
        )

    assert resp.status_code == 403


def test_get_workspace_root_from_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import ModuleType

    from app.api.files import evicted as evicted_module

    monkeypatch.delenv("MYRM_WORKSPACE_ROOT", raising=False)
    registry_mod = ModuleType(
        "myrm_agent_harness.toolkits.code_execution.workspace.registry"
    )
    registry_mod.get_active_workspace_path = lambda: "/registry/workspace"
    monkeypatch.setitem(
        sys.modules,
        "myrm_agent_harness.toolkits.code_execution.workspace.registry",
        registry_mod,
    )
    monkeypatch.setattr(evicted_module, "is_local_mode", lambda: False)

    assert evicted_module._get_workspace_root() == "/registry/workspace"


def test_get_workspace_root_local_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    from types import ModuleType

    from app.api.files import evicted as evicted_module

    monkeypatch.delenv("MYRM_WORKSPACE_ROOT", raising=False)
    default_ws = tmp_path / ".myrm" / "workspace"
    default_ws.mkdir(parents=True)

    registry_mod = ModuleType(
        "myrm_agent_harness.toolkits.code_execution.workspace.registry"
    )
    registry_mod.get_active_workspace_path = lambda: (_ for _ in ()).throw(
        RuntimeError("no registry")
    )
    monkeypatch.setitem(
        sys.modules,
        "myrm_agent_harness.toolkits.code_execution.workspace.registry",
        registry_mod,
    )
    monkeypatch.setattr(evicted_module.os.path, "expanduser", lambda _p: str(tmp_path))
    monkeypatch.setattr(evicted_module, "is_local_mode", lambda: True)

    assert evicted_module._get_workspace_root() == str(default_ws)


@pytest.mark.asyncio
async def test_read_evicted_read_oserror_returns_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = "chat_oserror"
    filename = f"output_{uuid.uuid4().hex[:8]}.txt"
    evicted_dir = tmp_path / ".context" / chat_id / "evicted"
    evicted_dir.mkdir(parents=True)
    (evicted_dir / filename).write_text("data", encoding="utf-8")
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from app.api.files.evicted import router as evicted_router
    from fastapi import FastAPI

    def _raise_oserror(*_args: object, **_kwargs: object) -> None:
        raise OSError("read failed")

    monkeypatch.setattr("builtins.open", _raise_oserror)

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": chat_id, "filename": filename},
        )

    assert resp.status_code == 500
