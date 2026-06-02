"""
End-to-end test for Docker container persistence.

Tests:
1. Start Docker backend container
2. Create test data (Agent, Chat, Skill)
3. Stop container
4. Restart container
5. Verify data persists

Usage:
    pytest tests/e2e/test_docker_persistence_e2e.py -v -s
    
Requirements:
    - Docker and Docker Compose installed
    - docker-compose.yaml in myrm-agent-server directory
    - .env file with required API keys
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest


def _is_docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

pytestmark = pytest.mark.skipif(not _is_docker_available(), reason="Docker is not available")

pytestmark = pytest.mark.e2e

BASE_URL = "http://localhost:25808"
DOCKER_COMPOSE_DIR = str(Path(__file__).resolve().parents[2])
HEADERS = {"Content-Type": "application/json"}


def run_docker_command(args: list[str], check: bool = True, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a docker compose command."""
    cmd = ["docker", "compose", "--profile", "app"] + args
    return subprocess.run(
        cmd,
        cwd=cwd or DOCKER_COMPOSE_DIR,
        capture_output=True,
        text=True,
        check=check,
    )


def wait_for_backend_healthy(timeout: int = 60) -> bool:
    """Wait for backend to become healthy."""
    print(f"Waiting for backend to become healthy (timeout: {timeout}s)...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = httpx.get(f"{BASE_URL}/health", timeout=5.0)
            if response.status_code == 200:
                print("✅ Backend is healthy")
                return True
        except (httpx.RequestError, httpx.TimeoutException):
            pass
        
        time.sleep(2)
    
    print("❌ Backend health check timeout")
    return False


async def create_test_data(client: httpx.AsyncClient) -> dict[str, str]:
    """Create test data and return IDs for verification."""
    test_data = {}
    
    # 1. Create a custom agent
    print("\n--- Creating test agent ---")
    agent_payload = {
        "name": "E2E Persistence Test Agent",
        "description": "Test agent for persistence verification",
        "system_prompt": "You are a test agent for E2E persistence testing.",
        "model_selection": {"model": "gpt-4o-mini", "providerId": "openai"},
        "is_built_in": False,
    }
    
    response = await client.post("/api/v1/user-agents", json=agent_payload)
    assert response.status_code == 200, f"Failed to create agent: {response.text}"
    test_data["agent_id"] = response.json()["data"]["id"]
    print(f"✅ Created agent: {test_data['agent_id']}")
    
    # 2. Create a chat session
    print("\n--- Creating test chat ---")
    chat_id = str(uuid.uuid4())
    test_data["chat_id"] = chat_id
    
    # Send a message to create the chat
    chat_payload = {
        "query": "Hello, this is a persistence test message.",
        "chatId": chat_id,
        "agent_id": test_data["agent_id"],
    }
    
    # Use streaming endpoint to send message
    async with client.stream("POST", "/api/v1/agents/agent-stream", json=chat_payload) as response:
        assert response.status_code == 200, f"Chat failed: {await response.aread()}"
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "message":
                        # Just consume the stream
                        pass
                except Exception:
                    pass
    
    print(f"✅ Created chat: {chat_id}")
    
    # 3. Verify data exists
    print("\n--- Verifying test data ---")
    
    # Verify agent exists
    response = await client.get(f"/api/v1/user-agents/{test_data['agent_id']}")
    assert response.status_code == 200, f"Agent not found: {response.text}"
    print(f"✅ Agent verified: {test_data['agent_id']}")
    
    # Verify chat exists
    response = await client.get(f"/api/v1/chats/{chat_id}")
    assert response.status_code == 200, f"Chat not found: {response.text}"
    print(f"✅ Chat verified: {chat_id}")
    
    return test_data


async def verify_test_data(client: httpx.AsyncClient, test_data: dict[str, str]) -> None:
    """Verify that test data still exists after restart."""
    print("\n--- Verifying data persistence after restart ---")
    
    # Verify agent still exists
    response = await client.get(f"/api/v1/user-agents/{test_data['agent_id']}")
    assert response.status_code == 200, f"Agent not found after restart: {response.text}"
    agent_data = response.json()["data"]
    assert agent_data["name"] == "E2E Persistence Test Agent"
    print(f"✅ Agent persisted: {test_data['agent_id']}")
    
    # Verify chat still exists
    response = await client.get(f"/api/v1/chats/{test_data['chat_id']}")
    assert response.status_code == 200, f"Chat not found after restart: {response.text}"
    print(f"✅ Chat persisted: {test_data['chat_id']}")
    
    # Verify messages in chat
    response = await client.get(f"/api/v1/chats/{test_data['chat_id']}/messages")
    assert response.status_code == 200, f"Failed to get messages: {response.text}"
    messages = response.json()["data"]
    assert len(messages) > 0, "No messages found in chat after restart"
    print(f"✅ Chat messages persisted: {len(messages)} messages")


async def cleanup_test_data(client: httpx.AsyncClient, test_data: dict[str, str]) -> None:
    """Clean up test data."""
    print("\n--- Cleaning up test data ---")
    
    # Delete agent
    if "agent_id" in test_data:
        response = await client.delete(f"/api/v1/user-agents/{test_data['agent_id']}")
        if response.status_code in (200, 204):
            print(f"✅ Deleted agent: {test_data['agent_id']}")
        else:
            print(f"⚠️ Failed to delete agent: {response.text}")
    
    # Delete chat
    if "chat_id" in test_data:
        response = await client.delete(f"/api/v1/chats/{test_data['chat_id']}")
        if response.status_code in (200, 204):
            print(f"✅ Deleted chat: {test_data['chat_id']}")
        else:
            print(f"⚠️ Failed to delete chat: {response.text}")


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.skipif(not _is_docker_available(), reason="Docker is not available")
async def test_docker_container_persistence():
    """
    Test Docker container data persistence across restarts.
    
    This test:
    1. Starts the backend container using docker-compose
    2. Creates test data (agent, chat, messages)
    3. Stops the container
    4. Restarts the container
    5. Verifies that all data persists
    """
    print("\n" + "=" * 80)
    print("Starting Docker Container Persistence Test")
    print("=" * 80)
    
    test_data = {}
    
    try:
        # Step 1: Start Docker backend
        print("\n[1/6] Starting Docker backend container...")
        run_docker_command(["up", "-d", "backend"])
        
        # Wait for backend to become healthy
        if not wait_for_backend_healthy(timeout=60):
            pytest.fail("Backend failed to become healthy")
        
        # Step 2: Create test data
        print("\n[2/6] Creating test data...")
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=60.0) as client:
            test_data = await create_test_data(client)
        
        # Step 3: Stop container
        print("\n[3/6] Stopping Docker backend container...")
        run_docker_command(["stop", "backend"])
        print("✅ Container stopped")
        
        # Wait a bit to ensure clean shutdown
        time.sleep(2)
        
        # Step 4: Restart container
        print("\n[4/6] Restarting Docker backend container...")
        run_docker_command(["start", "backend"])
        
        # Wait for backend to become healthy again
        if not wait_for_backend_healthy(timeout=60):
            pytest.fail("Backend failed to become healthy after restart")
        
        # Step 5: Verify data persists
        print("\n[5/6] Verifying data persistence...")
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=60.0) as client:
            await verify_test_data(client, test_data)
        
        # Step 6: Cleanup
        print("\n[6/6] Cleaning up...")
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=60.0) as client:
            await cleanup_test_data(client, test_data)
        
        print("\n" + "=" * 80)
        print("🎉 Docker Container Persistence Test PASSED!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        
        # Try to cleanup even on failure
        if test_data:
            try:
                async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=60.0) as client:
                    await cleanup_test_data(client, test_data)
            except Exception:
                pass
        
        raise
    
    finally:
        # Always stop the container at the end
        print("\nStopping Docker backend container...")
        run_docker_command(["stop", "backend"], check=False)


if __name__ == "__main__":
    import asyncio
    
    asyncio.run(test_docker_container_persistence())
