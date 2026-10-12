"""Unit tests for Cross-Source Context Fabric and Project Entity Linker API (Item 153).

[INPUT]
- TestClient, FastAPI mock app, project registration payloads, extraction texts, sink candidates.

[OUTPUT]
- Asserts on /projects, /extract, /link, and /sink API endpoints.

[POS]
- Server-side test suite for Item 153 CrossSourceWorkContextFabricAndProjectEntityLinkerSuite.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.context_fabric_router import router as context_fabric_router

app = FastAPI()
app.include_router(context_fabric_router)
client = TestClient(app)


def test_register_and_list_projects_api() -> None:
    project_payload = {
        "project_id": "proj_beijing_01",
        "name": "北京站智慧枢纽",
        "aliases": ["北京站", "BJ-Hub"],
        "keywords": ["闸机", "安检", "客流"],
        "description": "北京站大客流疏导与智慧闸机改造",
        "status": "active",
    }
    resp = client.post("/context-fabric/projects", json=project_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == "proj_beijing_01"

    list_resp = client.get("/context-fabric/projects")
    assert list_resp.status_code == 200
    projects = list_resp.json()
    assert any(p["project_id"] == "proj_beijing_01" for p in projects)


def test_extract_context_entities_api() -> None:
    text_payload = {
        "text": "由@李四 负责上海虹桥行李托运系统改造，承诺在 2026-11-01 上线。阻塞点: 缺少海关数据联调权限。"
    }
    resp = client.post("/context-fabric/extract", json=text_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] >= 3
    entity_types = {e["entity_type"] for e in data["entities"]}
    assert "person" in entity_types
    assert "commitment" in entity_types
    assert "blocker" in entity_types


def test_link_text_to_projects_api() -> None:
    # Register project first
    client.post(
        "/context-fabric/projects",
        json={
            "project_id": "proj_linear_42",
            "name": "重构 2.0",
            "aliases": ["Refactor-v2", "重构二期"],
            "keywords": ["AST", "解耦", "性能优化"],
        },
    )

    link_payload = {
        "text": "本次在 Refactor-v2 中针对 AST 编译与解耦的专项性能优化成果斐然",
        "min_confidence": 0.4,
    }
    resp = client.post("/context-fabric/link", json=link_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matches"]) >= 1
    assert data["top_project_id"] == "proj_linear_42"
    assert data["matches"][0]["confidence_score"] >= 0.6


def test_sink_project_insight_api() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Register target project
        client.post(
            "/context-fabric/projects",
            json={
                "project_id": "proj_beijing_sink",
                "name": "北京站",
                "aliases": ["BJ-Station"],
                "keywords": ["闸机", "网络重试"],
            },
        )

        sink_payload = {
            "candidate": {
                "insight_id": "ins_api_01",
                "title": "北京站闸机网络重试超时调整",
                "content": "弱网环境下网络超时应缩短并启用本地断网离线凭证",
                "source_event_ids": ["feishu_chat_77", "audio_interview_transcript"],
                "target_project_id": "proj_beijing_sink",
                "impact_level": "high",
            },
            "workspace_dir": tmp_dir,
            "target_file_type": "PROJECT_STATE.md",
        }
        resp = client.post("/context-fabric/sink", json=sink_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["project_id"] == "proj_beijing_sink"
        assert "feishu_chat_77" in (data["provenance_tag"] or "")

        # Verify physical write to workspace PROJECT_STATE.md
        state_file = Path(tmp_dir) / ".myrm" / "project" / "PROJECT_STATE.md"
        assert state_file.exists()
        content = state_file.read_text(encoding="utf-8")
        assert "北京站" in content
        assert "网络重试超时调整" in content
