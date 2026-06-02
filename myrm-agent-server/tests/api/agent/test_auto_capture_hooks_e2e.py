import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    get_model_selection,
)


@pytest.mark.asyncio
async def test_auto_capture_user_edict(client: TestClient):
    """Test that user edicts are automatically captured and put into pending state."""
    model_selection = get_model_selection()
    
    # 1. Send a user edict
    import uuid
    request_data = {
        "messageId": f"msg-{uuid.uuid4().hex[:12]}",
        "chatId": "test-auto-capture-1",
        "query": "never use sudo for this project",
        "modelSelection": model_selection,
        "actionMode": "agent",
        "memoryRequireConfirmation": True,
        "enableMemoryAutoExtraction": False,
    }
    
    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data) as response:
        assert response.status_code == 200
        for _line in response.iter_lines():
            pass
    
    # Check pending memories
    pending_response = client.get("/api/v1/memory/pending")
    assert pending_response.status_code == 200
    pending_data = pending_response.json()
    
    # We should have a pending memory for the user edict
    found = False
    print(f"Pending data: {pending_data}")
    for item in pending_data.get("items", []):
        if "sudo" in item.get("content", "").lower() and item.get("memory_type") == "procedural":
            found = True
            break
            
    assert found, "User edict was not captured as a pending procedural memory"

