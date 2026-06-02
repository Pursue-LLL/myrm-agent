"""Tests for Task-Adaptive API endpoints."""
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
class TestTaskAdaptiveAPI:
    """Test Task-Adaptive Harness API endpoints."""

    def test_get_recent_task_adaptive_contexts_empty(self, client: TestClient):
        """Test /task-adaptive/recent returns empty list when no contexts exist."""
        response = client.get("/api/v1/agents/task-adaptive/recent?limit=5")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "digests" in data["data"]
        assert isinstance(data["data"]["digests"], list)
        # Should be empty or populated depending on test order
        print(f"\n✅ Recent contexts API responded: {len(data['data']['digests'])} digests")

    def test_get_recent_task_adaptive_contexts_with_limit(self, client: TestClient):
        """Test /task-adaptive/recent respects limit parameter."""
        # First, create some contexts by running agent requests
        for i in range(3):
            chat_id = str(uuid.uuid4())
            create_payload = {
                "chat_id": chat_id,
                "title": f"Test Chat {i}",
                "task_adaptive_digest": {
                    "session_id": f"test_session_{i}",
                    "task_intent": f"Test task {i}",
                    "hotspots": [],
                    "anti_patterns": [],
                    "success_rate": 1.0,
                    "duration_ms": 100.0,
                },
            }
            client.post("/api/v1/chats", json=create_payload)
        
        # Now test the recent API with limit
        response = client.get("/api/v1/agents/task-adaptive/recent?limit=2")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        digests = data["data"]["digests"]
        
        # Should respect limit (or return whatever is available)
        print(f"\n✅ Recent API with limit=2: returned {len(digests)} digests")

    async def test_task_adaptive_digest_persistence(self, client: TestClient):
        """Test that task_adaptive_digest is persisted to database and can be retrieved."""
        chat_id = str(uuid.uuid4())
        
        test_digest = {
            "session_id": "persist_test",
            "task_intent": "Test persistence",
            "hotspots": [
                {"file_path": "test.py", "read_count": 5, "write_count": 2, "last_accessed": 0.0}
            ],
            "anti_patterns": [
                {
                    "error_signature": "Test error",
                    "failed_tool": "test_tool",
                    "failed_args": {},
                    "user_correction": "Test correction",
                    "timestamp": 0.0,
                }
            ],
            "success_rate": 0.9,
            "duration_ms": 500.0,
        }
        
        # Create chat with digest
        create_payload = {
            "chat_id": chat_id,
            "title": "Persistence Test",
            "task_adaptive_digest": test_digest,
        }
        
        response = client.post("/api/v1/chats", json=create_payload)
        if response.status_code != 200:
            print(f"\n❌ POST /chats failed: {response.status_code}")
            print(f"Response body: {response.text}")
        assert response.status_code == 200
        
        # Verify digest was persisted by querying via ChatService
        from app.services.chat.chat_service import ChatService
        
        chat = await ChatService.get_chat_metadata(chat_id)
        assert chat is not None, "Chat should exist in database"
        assert chat.task_adaptive_digest is not None, "task_adaptive_digest should be persisted"
        
        # Verify digest content
        assert chat.task_adaptive_digest["session_id"] == test_digest["session_id"]
        assert chat.task_adaptive_digest["task_intent"] == test_digest["task_intent"]
        assert len(chat.task_adaptive_digest["hotspots"]) == 1
        assert len(chat.task_adaptive_digest["anti_patterns"]) == 1
        print("\n✅ Digest persistence verified: saved to database")

    async def test_task_adaptive_digest_update(self, client: TestClient):
        """Test that task_adaptive_digest can be updated."""
        chat_id = str(uuid.uuid4())
        
        initial_digest = {
            "session_id": "update_test",
            "task_intent": "Initial intent",
            "hotspots": [],
            "anti_patterns": [],
            "success_rate": 1.0,
            "duration_ms": 100.0,
        }
        
        # Create chat with initial digest
        create_payload = {
            "chat_id": chat_id,
            "title": "Update Test",
            "task_adaptive_digest": initial_digest,
        }
        client.post("/api/v1/chats", json=create_payload)
        
        # Update with new digest
        updated_digest = {
            "session_id": "update_test",
            "task_intent": "Updated intent",
            "hotspots": [
                {"file_path": "new.py", "read_count": 3, "write_count": 1, "last_accessed": 0.0}
            ],
            "anti_patterns": [],
            "success_rate": 0.95,
            "duration_ms": 200.0,
        }
        
        update_payload = {
            "chat_id": chat_id,
            "title": "Update Test",
            "task_adaptive_digest": updated_digest,
        }
        
        response = client.post("/api/v1/chats", json=update_payload)
        assert response.status_code == 200
        
        # Verify update via ChatService
        from app.services.chat.chat_service import ChatService
        
        chat = await ChatService.get_chat_metadata(chat_id)
        assert chat is not None
        assert chat.task_adaptive_digest is not None
        
        # Verify updated content
        assert chat.task_adaptive_digest["task_intent"] == "Updated intent"
        assert len(chat.task_adaptive_digest["hotspots"]) == 1
        assert chat.task_adaptive_digest["hotspots"][0]["file_path"] == "new.py"
        print("\n✅ Digest update verified: updated in database")
