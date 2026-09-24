"""Tests for session event log and artifacts ZIP export pack endpoint."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from httpx import ASGITransport

from app.config.settings import settings
from app.database.models.artifact import Artifact, ArtifactVersion
from app.database.models.chat import Chat
from app.platform_utils import get_session_factory
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


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
async def test_export_pack_head_preflight(async_client: httpx.AsyncClient) -> None:
    chat_id = "test-export-head-1"
    factory = get_session_factory()
    async with factory() as db:
        chat = Chat(
            id=chat_id,
            title="测试标题 Preflight",
            source="web",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(chat)
        await db.commit()

    # 1. 正常 HEAD
    head_resp = await async_client.head(f"/api/v1/chats/{chat_id}/export-pack")
    assert head_resp.status_code == 200
    assert "application/zip" in head_resp.headers["content-type"]
    assert "Content-Disposition" in head_resp.headers
    assert "session_" in head_resp.headers["Content-Disposition"]

    # 2. 不存在的会话 HEAD
    non_existent = await async_client.head("/api/v1/chats/non-existent-chat-id/export-pack")
    assert non_existent.status_code == 404

    # 3. 非法路径穿越字符
    bad_resp = await async_client.head("/api/v1/chats/..%2F..%2Fbad/export-pack")
    assert bad_resp.status_code in (404, 422)


@pytest.mark.asyncio
async def test_export_pack_get_zip_content(
    async_client: httpx.AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = "test-export-get-1"
    log_dir = tmp_path / "event_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings.database, "event_log_dir", str(log_dir))

    # 创建会话元数据
    factory = get_session_factory()
    async with factory() as db:
        chat = Chat(
            id=chat_id,
            title="Python 重构任务",
            source="web",
            total_calls=5,
            total_tokens=1500,
            total_usd=0.03,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(chat)

        # 创建工件及版本
        workspace_root = tmp_path / "workspace"
        vault_objects = workspace_root / ".agent" / "vault" / "objects"
        vault_objects.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("app.api.chats.chat.export_pack.get_workspace_root", lambda: workspace_root)

        art_id = "art-patch-001"
        ver_id = "ver-001"
        artifact_content = b"diff --git a/foo.py b/foo.py\n+print('hello')"
        (vault_objects / ver_id).write_bytes(artifact_content)

        artifact = Artifact(
            id=art_id,
            chat_id=chat_id,
            name="patch.diff",
            is_deleted=False,
        )
        db.add(artifact)

        version = ArtifactVersion(
            id=ver_id,
            artifact_id=art_id,
            vault_uri=f"vault://{ver_id}",
            sha256_hash="dummy",
        )
        db.add(version)
        await db.commit()

    # 写入根事件日志
    raw_event = json.dumps(
        {
            "seq": 1,
            "ts": 1700000000.0,
            "type": "tool_start",
            "sid": chat_id,
            "data": {"tool": "bash", "command": "pytest --secret=sk-ant-api03-abcdefg"},
        }
    ) + "\n"
    (log_dir / f"{chat_id}.jsonl").write_text(raw_event, encoding="utf-8")

    # 写入子智能体日志
    sub_raw_event = json.dumps(
        {
            "seq": 1,
            "ts": 1700000001.0,
            "type": "subagent_step",
            "sid": f"{chat_id}_sub1",
            "data": {"msg": "subagent executing"},
        }
    ) + "\n"
    (log_dir / f"{chat_id}_sub1.jsonl").write_text(sub_raw_event, encoding="utf-8")

    resp = await async_client.get(f"/api/v1/chats/{chat_id}/export-pack?redact_secrets=true")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "Content-Disposition" in resp.headers

    # 解压 ZIP 并验证结构
    zip_bytes = resp.content
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        assert "session.jsonl" in namelist
        assert "subagents/sub1/session.jsonl" in namelist
        assert any(name.startswith("artifacts/patch.diff/") for name in namelist)

        # 校验 manifest.json
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["schema_version"] == "1.0"
        assert manifest["chat"]["id"] == chat_id
        assert manifest["chat"]["title"] == "Python 重构任务"
        assert manifest["options"]["redact_secrets"] is True
        assert manifest["integrity_report"]["total_files"] >= 3

        # 校验脱敏
        session_log_content = zf.read("session.jsonl").decode("utf-8")
        assert "sk-ant-api03-abcdefg" not in session_log_content
        assert "sk-ant...defg" in session_log_content

        # 校验工件内容完整性
        art_file = [name for name in namelist if name.startswith("artifacts/patch.diff/")][0]
        assert zf.read(art_file) == artifact_content


@pytest.mark.asyncio
async def test_export_pack_get_options_and_errors(
    async_client: httpx.AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. 不存在或不合法的会话 GET
    resp_404 = await async_client.get("/api/v1/chats/non-existent-chat/export-pack")
    assert resp_404.status_code == 404

    resp_bad = await async_client.get("/api/v1/chats/..%2F..%2Fbad/export-pack")
    assert resp_bad.status_code in (404, 422)

    # 2. 正常会话：关闭脱敏，关闭工件，关闭子agent
    chat_id = "test-export-options-1"
    log_dir = tmp_path / "event_logs_opt"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings.database, "event_log_dir", str(log_dir))

    factory = get_session_factory()
    async with factory() as db:
        chat = Chat(
            id=chat_id,
            title="Options Test",
            source="web",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(chat)
        await db.commit()

    raw_event = json.dumps(
        {
            "seq": 1,
            "ts": 1700000000.0,
            "type": "tool_start",
            "sid": chat_id,
            "data": {"secret": "sk-ant-raw-secret"},
        }
    ) + "\n"
    (log_dir / f"{chat_id}.jsonl").write_text(raw_event, encoding="utf-8")

    resp = await async_client.get(
        f"/api/v1/chats/{chat_id}/export-pack?redact_secrets=false&include_artifacts=false&include_subagents=false"
    )
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
        namelist = zf.namelist()
        assert "session.jsonl" in namelist
        assert not any(name.startswith("artifacts/") for name in namelist)
        assert not any(name.startswith("subagents/") for name in namelist)

        # 验证未脱敏
        raw_log = zf.read("session.jsonl").decode("utf-8")
        assert "sk-ant-raw-secret" in raw_log


def test_export_pack_internal_helpers(tmp_path: Path) -> None:
    from app.api.chats.chat.export_pack import (
        _build_content_disposition,
        _is_path_strictly_within,
        _sanitize_arcname,
        _ZipStreamBuffer,
    )

    # 1. _sanitize_arcname
    assert _sanitize_arcname("../../../etc/passwd") == "etc/passwd"
    assert _sanitize_arcname("foo/../bar/../../outside") == "foo/bar/outside"
    assert _sanitize_arcname("safe/path.diff") == "safe/path.diff"

    # 2. _is_path_strictly_within
    base = tmp_path / "base"
    base.mkdir()
    child = base / "child.txt"
    child.write_text("ok")
    assert _is_path_strictly_within(child, base) is True

    outside = tmp_path / "outside.txt"
    outside.write_text("evil")
    assert _is_path_strictly_within(outside, base) is False

    # 3. _build_content_disposition
    disp_empty = _build_content_disposition(None, "chat123456")
    assert "session_chat_" in disp_empty

    disp_cjk = _build_content_disposition("测试中文 会话", "chat123456")
    assert "UTF-8''" in disp_cjk

    # 4. _ZipStreamBuffer
    buf = _ZipStreamBuffer()
    buf.write(b"data1")
    buf.write(b"data2")
    buf.flush()
    assert buf.read_and_clear() == b"data1data2"
    assert buf.read_and_clear() == b""


@pytest.mark.asyncio
async def test_export_pack_direct_route_invocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.chats.chat.export_pack import export_chat_pack, preflight_export_pack

    chat_id = "test-direct-pack-1"
    log_dir = tmp_path / "logs_direct"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings.database, "event_log_dir", str(log_dir))

    factory = get_session_factory()
    async with factory() as db:
        chat = Chat(
            id=chat_id,
            title="Direct Test",
            source="web",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(chat)
        await db.commit()

        # Direct preflight invocation
        head_res = await preflight_export_pack(chat_id=chat_id, db=db)
        assert head_res.status_code == 200

        # Direct GET streaming invocation
        get_res = await export_chat_pack(chat_id=chat_id, db=db)
        assert get_res.media_type == "application/zip"

        # Preflight unsafe ID & not found
        with pytest.raises(HTTPException) as exc_info:
            await preflight_export_pack(chat_id="unsafe/../id", db=db)
        assert exc_info.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info:
            await preflight_export_pack(chat_id="non-existent-id", db=db)
        assert exc_info.value.status_code == 404

        # Export unsafe ID & not found
        with pytest.raises(HTTPException) as exc_info:
            await export_chat_pack(chat_id="unsafe/../id", db=db)
        assert exc_info.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info:
            await export_chat_pack(chat_id="non-existent-id", db=db)
        assert exc_info.value.status_code == 404



