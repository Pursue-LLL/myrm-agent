import os
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

# Must be set before importing the app (SQLite and storage paths)
_test_root = os.environ.get("MYRM_TEST_DIR", "/tmp/myrm_test")
if not os.environ.get("MYRM_DATA_DIR"):
    os.environ["MYRM_DATA_DIR"] = _test_root
if not os.environ.get("MYRM_DLQ_DIR"):
    os.environ["MYRM_DLQ_DIR"] = f"{_test_root}/dlq"


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    from tests.support.minimal_app import build_minimal_app
    app = build_minimal_app(preset="eval")
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.e2e
def test_dataset_crud_e2e(client: TestClient) -> None:
    dataset_id = "test_dataset_e2e"
    content = '{"message": "Calculate 5+5", "expected_tools": []}\n'

    # 1. Update/Create Dataset
    resp = client.put(f"/api/v1/eval/datasets/{dataset_id}", json={"content": content})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # 2. Get Dataset
    resp = client.get(f"/api/v1/eval/datasets/{dataset_id}")
    assert resp.status_code == 200
    assert resp.json()["content"] == content

    # 3. List Datasets
    resp = client.get("/api/v1/eval/datasets")
    assert resp.status_code == 200
    datasets = resp.json()["datasets"]
    assert any(d["id"] == dataset_id for d in datasets)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_capture_case_from_chat_e2e(client: TestClient) -> None:
    import uuid

    from app.services.chat.chat_service import ChatService

    chat_id = f"test_chat_e2e_{uuid.uuid4().hex[:8]}"
    dataset_name = "test_captured_dataset"
    now = datetime.now(tz=timezone.utc)

    # Pre-populate chat history
    await ChatService.ensure_chat_and_append_user_message(chat_id, "Test User Input", sent_at=now, sent_timezone="UTC")
    await ChatService.persist_assistant_message_safe(chat_id, "Test Assistant Response", timezone="UTC")

    # Capture case
    resp = client.post(f"/api/v1/eval/cases/from-chat/{chat_id}?dataset_id={dataset_name}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Verify the captured case is in the dataset
    resp = client.get(f"/api/v1/eval/datasets/{dataset_name}")
    assert resp.status_code == 200
    content = resp.json()["content"]
    assert "Test User Input" in content
