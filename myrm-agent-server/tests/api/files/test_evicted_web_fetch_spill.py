"""Integration tests: evicted API reads UECD spill files."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.context_management.infra.evicted import (
    EVICTED_BASENAME_PATTERN,
    normalize_delivery_chat_id,
    write_evicted_content_sync,
)
from myrm_agent_harness.core.context_vars import chat_id_var, workspace_root_var


@pytest.fixture(autouse=True)
def _evicted_api_prefer_env_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    """ASGI tests seed MYRM_WORKSPACE_ROOT; skip DB chat workspace resolution."""

    async def _skip_chat_workspace(
        _chat_id: str, *, persist_workspace: bool = False
    ) -> None:
        return None

    monkeypatch.setattr(
        "app.services.agent.params.workspace_resolve.resolve_default_chat_workspace_dir",
        _skip_chat_workspace,
    )


def _evicted_dir(tmp_path: Path, chat_id: str) -> Path:
    normalized = normalize_delivery_chat_id(chat_id)
    directory = tmp_path / ".context" / normalized / "evicted"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_server_filename_pattern_matches_harness_ssot() -> None:
    from app.api.files.evicted import _FILENAME_PATTERN

    assert _FILENAME_PATTERN.pattern == EVICTED_BASENAME_PATTERN.pattern


@pytest.mark.asyncio
async def test_read_evicted_web_fetch_md_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = "chat_web_fetch_spill"
    filename = f"web_fetch_{uuid.uuid4().hex[:8]}.md"
    evicted_dir = _evicted_dir(tmp_path, chat_id)
    content = "# Title\n\n" + ("paragraph\n" * 50)
    (evicted_dir / filename).write_text(content, encoding="utf-8")

    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from fastapi import FastAPI

    from app.api.files.evicted import router as evicted_router

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
async def test_read_evicted_paginated_slice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = "chat_paginated"
    filename = f"tool_{uuid.uuid4().hex[:8]}.txt"
    evicted_dir = _evicted_dir(tmp_path, chat_id)
    content = "line\n" * 1200
    (evicted_dir / filename).write_text(content, encoding="utf-8")

    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from fastapi import FastAPI

    from app.api.files.evicted import router as evicted_router

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": chat_id, "filename": filename, "offset": 500, "limit": 100},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["offset"] == 500
    assert data["limit"] == 100
    assert data["total_lines"] == 1200
    assert data["content"].count("line\n") == 100


@pytest.mark.asyncio
async def test_read_evicted_rejects_limit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = "chat_limit_zero"
    filename = f"tool_{uuid.uuid4().hex[:8]}.txt"
    evicted_dir = _evicted_dir(tmp_path, chat_id)
    (evicted_dir / filename).write_text("line\n", encoding="utf-8")

    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from fastapi import FastAPI

    from app.api.files.evicted import router as evicted_router

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": chat_id, "filename": filename, "offset": 0, "limit": 0},
        )

    assert resp.status_code == 422


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

        from fastapi import FastAPI

        from app.api.files.evicted import router as evicted_router

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
                    "limit": 500,
                },
            )

        assert resp.status_code == 200
        page = resp.json()
        assert page["total_lines"] == result.total_lines
        assert page["offset"] == 0
        assert page["limit"] == 500
        assert page["content"].startswith("payload\n")
        assert page["content"].count("payload\n") == 500
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)


@pytest.mark.asyncio
async def test_read_evicted_normalizes_chat_id_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_chat_id = "chat_prefix_norm"
    filename = f"output_{uuid.uuid4().hex[:8]}.txt"
    evicted_dir = _evicted_dir(tmp_path, api_chat_id)
    (evicted_dir / filename).write_text("normalized\n", encoding="utf-8")
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from fastapi import FastAPI

    from app.api.files.evicted import router as evicted_router

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": api_chat_id, "filename": filename, "offset": 0, "limit": 10},
        )

    assert resp.status_code == 200
    assert "normalized" in resp.json()["content"]


@pytest.mark.asyncio
async def test_read_evicted_rejects_invalid_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from fastapi import FastAPI

    from app.api.files.evicted import router as evicted_router

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

    from fastapi import FastAPI

    from app.api.files.evicted import router as evicted_router

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

    from fastapi import FastAPI

    from app.api.files.evicted import router as evicted_router

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": "chat_missing", "filename": filename},
        )

    assert resp.status_code == 404
    body = resp.json()
    assert body.get("expired") is True


@pytest.mark.asyncio
async def test_read_evicted_workspace_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MYRM_WORKSPACE_ROOT", raising=False)
    filename = f"output_{uuid.uuid4().hex[:8]}.txt"

    from fastapi import FastAPI

    from app.api.files import evicted as evicted_module
    from app.api.files.evicted import router as evicted_router

    async def _unavailable_workspace(_chat_id: str) -> None:
        return None

    monkeypatch.setattr(evicted_module, "_get_workspace_root", lambda: None)
    monkeypatch.setattr(
        evicted_module, "_get_evicted_workspace_root", _unavailable_workspace
    )

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

    from fastapi import FastAPI

    from app.api.files.evicted import router as evicted_router

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

    from fastapi import FastAPI

    from app.api.files.evicted import router as evicted_router

    evicted_dir = _evicted_dir(tmp_path, chat_id)
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
    evicted_dir = _evicted_dir(tmp_path, chat_id)
    (evicted_dir / filename).write_text("data", encoding="utf-8")
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from fastapi import FastAPI

    from app.api.files import evicted as evicted_module
    from app.api.files.evicted import router as evicted_router

    def _raise_oserror(*_args: object, **_kwargs: object) -> object:
        raise OSError("read failed")

    monkeypatch.setattr(evicted_module, "read_evicted_line_range", _raise_oserror)

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": chat_id, "filename": filename},
        )

    assert resp.status_code == 500
