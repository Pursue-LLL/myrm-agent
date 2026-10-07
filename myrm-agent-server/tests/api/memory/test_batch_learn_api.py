"""[POS]: tests/api/memory/test_batch_learn_api.py
[INPUT]: None.
[OUTPUT]: Isolated integration tests for batch memory distillation, namespaced ID retrieval, and single-item undo API.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.batch_learn import router
from app.services.memory.batch_learn import BatchMemoryLearningProvider


@pytest.fixture(autouse=True)
def setup_isolated_batch_learning_provider(tmp_path: Path):
    db_file = tmp_path / "test_api_batch.db"
    BatchMemoryLearningProvider.set_custom_db_path(db_file)
    yield
    BatchMemoryLearningProvider.reset()


@pytest.mark.asyncio
async def test_batch_learn_full_lifecycle_api() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/memory")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Execute batch learn
        learn_req = {
            "chunks": [
                {
                    "chunk_index": 0,
                    "raw_text": "- Always adhere to strict static typing.\n- Write clean modular functions.",
                    "metadata": {"source_doc": "guide.md"},
                },
                {
                    "chunk_index": 1,
                    "raw_text": "- User prefers dark mode theme across development tools.",
                    "metadata": {"source_doc": "profile.md"},
                },
            ],
            "scope": "workspace_test",
            "sub_scope": "user_101",
            "category": "preferences",
        }

        resp = await client.post("/api/memory/batch-learn/learn", json=learn_req)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_chunks"] == 2
        assert data["successful_chunks"] == 2
        assert data["failed_chunks"] == 0
        assert data["total_items_learned"] == 3
        assert len(data["items"]) == 3
        assert len(data["chunk_diagnostics"]) == 2

        batch_id = data["batch_id"]
        first_item = data["items"][0]
        first_ns_id = first_item["namespaced_id"]
        assert first_ns_id.startswith("mem:workspace_test:user_101:preferences:")
        assert first_item["status"] == "active"

        # 2. Get specific item by namespaced ID
        item_resp = await client.get(f"/api/memory/batch-learn/item/{first_ns_id}")
        assert item_resp.status_code == 200
        item_data = item_resp.json()
        assert item_data["namespaced_id"] == first_ns_id
        assert item_data["status"] == "active"

        # 3. Undo / Revoke the single item
        undo_resp = await client.post(
            "/api/memory/batch-learn/undo",
            json={"namespaced_id": first_ns_id},
        )
        assert undo_resp.status_code == 200
        undo_data = undo_resp.json()
        assert undo_data["success"] is True
        assert undo_data["namespaced_id"] == first_ns_id

        # 4. Verify item status changed to revoked
        verify_resp = await client.get(f"/api/memory/batch-learn/item/{first_ns_id}")
        assert verify_resp.status_code == 200
        assert verify_resp.json()["status"] == "revoked"

        # 5. Idempotent undo returns success=False
        undo_again_resp = await client.post(
            "/api/memory/batch-learn/undo",
            json={"namespaced_id": first_ns_id},
        )
        assert undo_again_resp.status_code == 200
        assert undo_again_resp.json()["success"] is False

        # 6. List items by batch ID
        batch_items_resp = await client.get(f"/api/memory/batch-learn/batch/{batch_id}/items")
        assert batch_items_resp.status_code == 200
        batch_items_data = batch_items_resp.json()
        assert batch_items_data["batch_id"] == batch_id
        assert batch_items_data["total_items"] == 3

        # 7. Query non-existent item returns 404
        non_existent_resp = await client.get("/api/memory/batch-learn/item/mem:scope:sub:cat:nonexistent")
        assert non_existent_resp.status_code == 404
