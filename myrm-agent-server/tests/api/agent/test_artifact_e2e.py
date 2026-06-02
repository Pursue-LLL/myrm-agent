"""Artifact E2E Tests

Tests the full lifecycle of an artifact:
1. Agent generates a file.
2. Listener persists it to the Vault and DB.
3. Frontend queries the artifact list.
4. Frontend verifies the artifact hash (testing the streaming verify endpoint).
"""

from __future__ import annotations

import json
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    get_model_selection,
    get_search_service_config,
)


def _run_agent_until_settled(
    client: TestClient, req_data: dict[str, object]
) -> list[dict[str, object]]:
    collected_data: list[dict[str, object]] = []
    for _round_idx in range(5):
        with client.stream(
            "POST", "/api/v1/agents/agent-stream", json=req_data
        ) as response:
            if response.status_code != 200:
                print(
                    f"Error {response.status_code}: {response.read().decode('utf-8')}"
                )
            assert response.status_code == 200
            for line in response.iter_lines():
                print(f"Raw line: {line!r}", flush=True)
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    if isinstance(data, dict):
                        print(f"Received event: {data.get('type')}", flush=True)
                        collected_data.append(data)
                except json.JSONDecodeError:
                    continue

        approval_required = any(
            data.get("type") in ("approval_required", "tool_approval_request")
            for data in collected_data[-10:]
        )
        if not approval_required:
            break

        req_data["resumeValue"] = [
            {"type": "approve", "extensions": {"allowAlways": True}}
        ]

    error_events = [d for d in collected_data if d.get("type") == "error"]
    if error_events:
        pytest.fail(f"Agent execution error: {error_events[0].get('error')}")
    return collected_data


def _poll_target_artifact(
    client: TestClient,
    *,
    filename: str,
    attempts: int = 12,
    interval_s: float = 0.5,
) -> dict[str, object] | None:
    for _ in range(attempts):
        res = client.get("/api/v1/files/artifacts/")
        assert res.status_code == 200
        artifacts = res.json()["artifacts"]
        print(
            f"[DEBUG] Polled artifacts: {[a.get('name') for a in artifacts]}",
            flush=True,
        )
        for artifact in artifacts:
            if artifact.get("name") == filename:
                return artifact
        time.sleep(interval_s)
    return None


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestArtifactE2E:
    """Artifact E2E Tests"""

    def test_artifact_lifecycle(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test the full lifecycle of an artifact."""
        monkeypatch.setenv("BASIC_MODEL", "minimax/MiniMax-M2.7")
        monkeypatch.setenv("BASIC_API_KEY", os.environ.get("LITE_API_KEY", ""))
        monkeypatch.setenv("BASIC_BASE_URL", os.environ.get("LITE_BASE_URL", ""))

        model_selection = get_model_selection()
        search_config = get_search_service_config()
        query = (
            "Call file_write_tool NOW. Write exactly '# Hello Artifact' to hello_artifact.md. "
            "Do NOT use bash_code_execute_tool or planner_tool."
        )

        target_artifact: dict[str, object] | None = None
        for attempt in range(3):
            chat_id = f"test-artifact-{uuid.uuid4().hex[:8]}"
            req_data: dict[str, object] = {
                "messageId": f"test-msg-{attempt}",
                "chatId": chat_id,
                "query": query,
                "modelSelection": model_selection,
                "searchServiceCfg": search_config,
                "agentConfig": {"enabledBuiltinTools": ["file_write_tool"]},
            }
            _run_agent_until_settled(client, req_data)
            target_artifact = _poll_target_artifact(
                client, filename="hello_artifact.md"
            )
            if target_artifact is not None:
                break

        assert (
            target_artifact is not None
        ), "hello_artifact.md was not found after 3 attempts"

        artifact_id = str(target_artifact["id"])
        res = client.get(f"/api/v1/files/artifacts/{artifact_id}/versions")
        assert res.status_code == 200
        versions = res.json()["versions"]
        assert len(versions) > 0, "Artifact should have at least one version"

        version_id = versions[0]["id"]
        res = client.post(f"/api/v1/files/artifacts/{artifact_id}/verify/{version_id}")
        assert res.status_code == 200
        verify_result = res.json()
        assert verify_result["is_valid"] is True, "Hash verification failed!"
        assert verify_result["expected_hash"] == verify_result["actual_hash"]
