"""Unit tests for Auto Memory Staleness Decay and Consolidation Audit API (Item 158).

[INPUT]
- FastAPI TestClient, memory registration payloads, touch recall requests, audit and consolidation bodies.

[OUTPUT]
- Asserts verifying /staleness-consolidation/memories, /touch-recall, /audit, /consolidate, /archive endpoints.

[POS]
- Server-side test suite in myrm-agent-server/tests/api/memory/test_staleness_consolidation_api.py.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.staleness_consolidation_router import (
    router as staleness_consolidation_router,
)

app = FastAPI()
app.include_router(staleness_consolidation_router)
client = TestClient(app)


def test_register_and_get_memory_api() -> None:
    mem_id = "test_mem_reg_01"
    reg_payload = {
        "memory_id": mem_id,
        "content": "User prefers concise architectural explanations",
        "category": "communication",
        "created_at": "2026-10-10T10:00:00Z",
        "referenced_paths": ["README.md"],
        "referenced_assertions": [],
    }
    resp = client.post("/staleness-consolidation/memories", json=reg_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["memory_id"] == mem_id
    assert data["status"] == "active"
    assert data["category"] == "communication"

    # Get by ID
    get_resp = client.get(f"/staleness-consolidation/memories/{mem_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["memory_id"] == mem_id

    # List all
    list_resp = client.get("/staleness-consolidation/memories", params={"status": "active"})
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(it["memory_id"] == mem_id for it in items)


def test_touch_recall_api() -> None:
    mem_id = "test_mem_touch_02"
    client.post(
        "/staleness-consolidation/memories",
        json={
            "memory_id": mem_id,
            "content": "Use uv for fast python package management",
            "category": "tooling",
            "created_at": "2026-10-10T10:00:00Z",
        },
    )

    touch_resp = client.post(
        "/staleness-consolidation/touch-recall",
        json={"memory_id": mem_id, "now_iso": "2026-10-10T12:00:00Z"},
    )
    assert touch_resp.status_code == 200
    data = touch_resp.json()
    assert data["memory_id"] == mem_id
    assert data["recalled_count"] == 1
    assert data["status"] == "active"


def test_run_audit_api() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "app.py").write_text("# entry", encoding="utf-8")

        client.post(
            "/staleness-consolidation/memories",
            json={
                "memory_id": "test_audit_03",
                "content": "FastAPI entry point exists",
                "category": "backend",
                "created_at": "2026-10-10T10:00:00Z",
                "referenced_paths": ["app.py"],
            },
        )

        audit_resp = client.post(
            "/staleness-consolidation/audit",
            json={"workspace_dir": tmp_dir, "now_iso": "2026-10-10T12:00:00Z"},
        )
        assert audit_resp.status_code == 200
        report = audit_resp.json()
        assert report["total_items"] >= 1
        assert "generated_at" in report


def test_apply_consolidation_api() -> None:
    # 1. Register 2 fragmented memories in category 'database'
    client.post(
        "/staleness-consolidation/memories",
        json={
            "memory_id": "frag_db_01",
            "content": "Use SQLite WAL mode for local concurrency",
            "category": "database",
            "created_at": "2026-10-10T10:00:00Z",
        },
    )
    client.post(
        "/staleness-consolidation/memories",
        json={
            "memory_id": "frag_db_02",
            "content": "Set busy timeout to 5000ms for busy lock retry",
            "category": "database",
            "created_at": "2026-10-10T10:00:00Z",
        },
    )

    # 2. Run audit to discover proposal
    audit_resp = client.post(
        "/staleness-consolidation/audit",
        json={"workspace_dir": None, "now_iso": "2026-10-10T12:00:00Z"},
    )
    report = audit_resp.json()
    db_proposals = [p for p in report["consolidation_proposals"] if p["category"] == "database"]
    assert len(db_proposals) >= 1

    prop_id = db_proposals[0]["proposal_id"]

    # 3. Apply consolidation
    cons_resp = client.post(
        "/staleness-consolidation/consolidate",
        json={"proposal_id": prop_id, "now_iso": "2026-10-10T12:00:00Z"},
    )
    assert cons_resp.status_code == 200
    new_mem = cons_resp.json()
    assert new_mem["memory_id"].startswith("mem_cons_")
    assert new_mem["status"] == "active"
    assert new_mem["category"] == "database"


def test_archive_memories_api() -> None:
    mem_id = "test_mem_arch_05"
    client.post(
        "/staleness-consolidation/memories",
        json={
            "memory_id": mem_id,
            "content": "Temporary scratch note to be archived",
            "category": "temp",
            "created_at": "2026-10-10T10:00:00Z",
        },
    )

    arch_resp = client.post(
        "/staleness-consolidation/archive",
        json={"memory_ids": [mem_id]},
    )
    assert arch_resp.status_code == 200
    archived_ids = arch_resp.json()
    assert mem_id in archived_ids

    # Verify status changed to archived
    item_resp = client.get(f"/staleness-consolidation/memories/{mem_id}")
    assert item_resp.status_code == 200
    assert item_resp.json()["status"] == "archived"
