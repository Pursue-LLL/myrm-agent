"""Persist `auto_restore_domains` on user agents (CRUD round-trip)."""

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_auto_restore_domains_create_and_get_roundtrip() -> None:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"AutoRestore CRUD {suffix}",
        "description": "auto restore persistence test",
        "system_prompt": "You are a test agent.",
        "is_built_in": False,
        "enabled_builtin_tools": ["browser", "web_search"],
        "auto_restore_domains": ["example.com", "github.com"],
    }
    created = client.post("/api/v1/user-agents", json=payload)
    assert created.status_code == 200, created.text
    agent_id = created.json()["data"]["id"]
    try:
        assert created.json()["data"]["auto_restore_domains"] == [
            "example.com",
            "github.com",
        ]

        loaded = client.get(f"/api/v1/user-agents/{agent_id}")
        assert loaded.status_code == 200, loaded.text
        assert loaded.json()["data"]["auto_restore_domains"] == [
            "example.com",
            "github.com",
        ]

        updated = client.put(
            f"/api/v1/user-agents/{agent_id}",
            json={"auto_restore_domains": ["wiki.example.org"]},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["auto_restore_domains"] == ["wiki.example.org"]
    finally:
        client.delete(f"/api/v1/user-agents/{agent_id}")
