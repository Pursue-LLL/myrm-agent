"""Integration tests for agent file security (Path Traversal defense)."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_agent_file_path_traversal_defense(async_client: AsyncClient, tmp_path: Path) -> None:
    """Test that the agent file endpoint prevents path traversal attacks."""

    print("\n🚀 Starting agent file path traversal security test...")

    # 1. Put a tiny png into a home directory the agent points at
    filename = "avatar.png"
    dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0aIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    agent_home = tmp_path / "agent-home"
    agent_home.mkdir()
    (agent_home / filename).write_bytes(dummy_png)

    # 2. Create a dummy agent whose home directory holds that file
    print("👤 Creating a test agent...")
    create_req = {
        "name": "Security Test Agent",
        "description": "Agent for testing path traversal",
        "home_directory": str(agent_home),
    }
    create_resp = await async_client.post("/api/agents", json=create_req)
    assert create_resp.status_code == 200, f"Failed to create agent: {create_resp.text}"
    agent_data = create_resp.json()["data"]
    agent_id = agent_data["id"]

    print(f"✅ Agent created: {agent_id}")

    # 3. Test retrieving the legitimate file
    print(f"📥 Testing legitimate file access: {filename}")
    get_resp = await async_client.get(f"/api/agents/{agent_id}/files/{filename}")
    assert get_resp.status_code == 200, "Legitimate file access failed"
    assert get_resp.content == dummy_png, "File content mismatch"
    print("✅ Legitimate file access passed")

    # 4. Test path traversal payloads
    print("🛡️ Testing malicious path traversal payloads...")

    malicious_payloads = [
        "../../../etc/passwd",
        "..%2F..%2F..%2Fetc%2Fpasswd",
        "/etc/passwd",
        "%00../../../etc/passwd",  # Null byte
    ]

    for payload in malicious_payloads:
        print(f"  🧪 Testing payload: {payload}")
        mal_resp = await async_client.get(f"/api/agents/{agent_id}/files/{payload}")
        # Expected to be blocked with 422 or 400 (validation error)
        assert mal_resp.status_code in (400, 422, 404), (
            f"Path traversal succeeded! Payload: {payload}, Status: {mal_resp.status_code}"
        )
        print(f"  ✅ Blocked with status: {mal_resp.status_code}")

    print("🎉 All security tests passed successfully!")
