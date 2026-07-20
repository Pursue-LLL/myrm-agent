"""Integration-style tests: evicted API reads background spill files."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_read_evicted_background_spill_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat_id = "chat-spill-read"
    filename = "output_deadbeef.txt"
    evicted_dir = tmp_path / ".context" / chat_id / "evicted"
    evicted_dir.mkdir(parents=True)
    (evicted_dir / filename).write_text("line-one\nline-two\n", encoding="utf-8")

    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from app.api.files.evicted import router as evicted_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": chat_id, "filename": filename},
        )

    assert res.status_code == 200
    body = res.json()
    assert "line-one" in body["content"]
    assert body["total_lines"] >= 2


@pytest.mark.asyncio
async def test_reject_legacy_background_spill_filename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat_id = "chat-legacy"
    legacy_name = "bg_job123.log"
    evicted_dir = tmp_path / ".context" / chat_id / "evicted"
    evicted_dir.mkdir(parents=True)
    (evicted_dir / legacy_name).write_text("legacy\n", encoding="utf-8")
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))

    from app.api.files.evicted import router as evicted_router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(evicted_router, prefix="/api/v1/files")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/v1/files/evicted",
            params={"chat_id": chat_id, "filename": legacy_name},
        )

    assert res.status_code == 400
    assert os.path.isfile(evicted_dir / legacy_name)
