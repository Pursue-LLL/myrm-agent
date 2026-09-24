"""Tests for session event log and artifacts ZIP export pack endpoint."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
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
