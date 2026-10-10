"""Unit tests for Project Experience & ADR Flywheel API (Item 154).

[INPUT]
- TestClient, FastAPI mock app, experience payloads, sniffing queries.

[OUTPUT]
- Asserts on /extract, /ingest, /list, and /sniff API endpoints.

[POS]
- Server-side test suite for Item 154 ProjectExperienceAndADRFlywheelSuite.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.experience_flywheel_router import router as experience_flywheel_router

app = FastAPI()
app.include_router(experience_flywheel_router)
client = TestClient(app)


def test_extract_experiences_api() -> None:
    narrative = """
    模块: `sqlite_pool`。踩坑记录：触发条件: 高并发读写时。根因: 缺少 WAL 模式开启。有效解法: 统一在初始化执行 PRAGMA journal_mode=WAL。
    模块: `jwt_auth`。架构决策 ADR：论据: 提高多端凭证安全性。约定: 必须采用 ED25519 非对称签名。
    """
    resp = client.post("/experience-flywheel/extract", json={"narrative": narrative})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] >= 2
    kinds = {e["kind"] for e in data["experiences"]}
    assert "bug_experience" in kinds
    assert "architectural_decision" in kinds


def test_ingest_and_list_experiences_api() -> None:
    payload = {
        "experience": {
            "experience_id": "exp_api_01",
            "kind": "bug_experience",
            "target_entity": "billing_worker",
            "trigger_condition": "账单重算并发触发",
            "root_cause_or_rationale": "未持分布式排他锁",
            "convention_or_remedy": "必须先获取 Redis 分布式租约锁",
            "created_date": "2026-09-28",
            "tags": ["billing", "lock"],
        }
    }
    ingest_resp = client.post("/experience-flywheel/ingest", json=payload)
    assert ingest_resp.status_code == 200
    ingest_data = ingest_resp.json()
    assert ingest_data["experience_id"] == "exp_api_01"
    assert ingest_data["persisted"] is True

    # List all
    list_resp = client.get("/experience-flywheel/list")
    assert list_resp.status_code == 200
    all_items = list_resp.json()
    assert any(e["experience_id"] == "exp_api_01" for e in all_items)

    # Filter by kind
    filter_resp = client.get("/experience-flywheel/list?kind=bug_experience")
    assert filter_resp.status_code == 200
    filtered_items = filter_resp.json()
    assert all(e["kind"] == "bug_experience" for e in filtered_items)


def test_sniff_minefield_api() -> None:
    # Ensure danger item is in store
    client.post(
        "/experience-flywheel/ingest",
        json={
            "experience": {
                "experience_id": "exp_danger_table",
                "kind": "bug_experience",
                "target_entity": "account_balance_table",
                "trigger_condition": "直接修改余额列",
                "root_cause_or_rationale": "缺少流水对账账本",
                "convention_or_remedy": "所有资金变更必须先写 ledger_entry 流水表",
                "created_date": "2026-09-28",
            }
        },
    )

    sniff_payload = {
        "plan_text": "准备直接对 account_balance_table 进行余额扣减优化",
        "explicit_entities": ["account_balance_table"],
    }
    resp = client.post("/experience-flywheel/sniff", json=sniff_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["alerts"]) >= 1
    assert data["has_critical_alerts"] is True
    assert "account_balance_table" in data["advisory_prompt"]
    assert "ledger_entry" in data["alerts"][0]["convention_to_follow"]


def test_ingest_with_dongle_persistence() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        payload = {
            "experience": {
                "experience_id": "exp_dongle_sync",
                "kind": "bug_experience",
                "target_entity": "cache_store",
                "trigger_condition": "单次大键写入",
                "root_cause_or_rationale": "导致集群超时",
                "convention_or_remedy": "限制单 key 小于 512KB",
                "created_date": "2026-09-28",
            },
            "workspace_dir": tmp_dir,
        }
        resp = client.post("/experience-flywheel/ingest", json=payload)
        assert resp.status_code == 200
        assert resp.json()["bound_dongle_block_id"] == "exp_dongle_sync"

        # Check file
        lessons_file = Path(tmp_dir) / ".myrm" / "project" / "LESSONS.md"
        assert lessons_file.exists()
        content = lessons_file.read_text(encoding="utf-8")
        assert "cache_store" in content
        assert "512KB" in content
