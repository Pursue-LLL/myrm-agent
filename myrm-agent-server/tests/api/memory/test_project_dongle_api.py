"""Unit tests for Project Context USB Dongle API endpoints (Item 152).

[INPUT]
- Temporary workspace directories, TestClient, FastAPI mock app.

[OUTPUT]
- Asserts on /dongle/init, /dongle/state, /dongle/prompt, and /dongle/sync endpoints.

[POS]
- Server-side test suite for Item 152 ProjectContextUsbDongleAndCrossAgentRelaySuite.
"""

from __future__ import annotations

import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.project_dongle_router import router as project_dongle_router

app = FastAPI()
app.include_router(project_dongle_router)
client = TestClient(app)


def test_init_project_dongle_api() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        resp = client.post("/dongle/init", json={"workspace_dir": tmp_dir})
        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_dir"] == tmp_dir
        assert len(data["initialized_files"]) == 4
        assert "PROJECT_STATE.md" in data["initialized_files"]
        assert "INDEX.md" in data["initialized_files"]


def test_get_dongle_state_api() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        # First initialize
        client.post("/dongle/init", json={"workspace_dir": tmp_dir})

        resp = client.get(f"/dongle/state?workspace_dir={tmp_dir}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_dir"] == tmp_dir
        assert isinstance(data["project_state_blocks"], list)
        assert isinstance(data["decision_blocks"], list)
        assert isinstance(data["lesson_blocks"], list)
        assert data["total_active_blocks"] == 0


def test_get_dongle_prompt_api() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        client.post("/dongle/init", json={"workspace_dir": tmp_dir})

        # Sync a block
        block_payload = {
            "block_id": "api-01",
            "block_type": "PROJECT_STATE.md",
            "content": "Verify zero-loss cross agent relay prompt",
            "created_date": "2026-09-27",
            "tags": ["relay", "test"],
        }
        client.post("/dongle/sync", json={"workspace_dir": tmp_dir, "blocks": [block_payload]})

        resp = client.get(f"/dongle/prompt?workspace_dir={tmp_dir}")
        assert resp.status_code == 200
        data = resp.json()
        assert "PROJECT CONTEXT DONGLE" in data["prompt_context"]
        assert "Verify zero-loss cross agent relay prompt" in data["prompt_context"]


def test_sync_project_dongle_blocks_api() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        blocks = [
            {
                "block_id": "dec-01",
                "block_type": "DECISIONS.md",
                "content": "Use FastAPI subrouters for modular memory endpoints",
                "created_date": "2026-09-27",
                "tags": ["architecture"],
            },
            {
                "block_id": "les-01",
                "block_type": "LESSONS.md",
                "content": "Do not import heavy main app during router tests",
                "created_date": "2026-09-27",
                "tags": ["testing"],
            },
        ]
        resp = client.post("/dongle/sync", json={"workspace_dir": tmp_dir, "blocks": blocks})
        assert resp.status_code == 200
        data = resp.json()
        assert data["added_blocks_count"] == 2
        assert "DECISIONS.md" in data["updated_files"]
        assert "LESSONS.md" in data["updated_files"]
        assert "INDEX.md" in data["updated_files"]

        # Verify state reflects added blocks
        state_resp = client.get(f"/dongle/state?workspace_dir={tmp_dir}")
        state_data = state_resp.json()
        assert state_data["total_active_blocks"] == 2
        assert len(state_data["decision_blocks"]) == 1
        assert len(state_data["lesson_blocks"]) == 1
