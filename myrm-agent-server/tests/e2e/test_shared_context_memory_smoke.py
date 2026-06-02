from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

import httpx
import pytest

_BASE_URL = os.getenv("MYRM_SMOKE_BASE_URL")
_CHAT_RECALL_ENABLED = os.getenv("MYRM_SMOKE_ENABLE_CHAT_RECALL") == "1"
_HEALTH_FIX_HINTS: dict[str, str] = {
    "missing_embedding_api_key": "Configure an embedding API key, or configure a reachable local embedding API base.",
    "placeholder_embedding_api_key": "Replace the placeholder embedding API key with a real secret.",
    "invalid_api_key": "Check the embedding provider key used by this runtime.",
    "insufficient_quota": "Check embedding provider quota or switch to a working embedding backend.",
    "rate_limited": "Retry later or use a less rate-limited embedding backend.",
    "timeout": "Check embedding provider latency and network reachability.",
    "network_error": "Check the embedding API base URL and network route from this runtime.",
    "embedding_probe_failed": "Check the embedding provider configuration and backend logs.",
}


def _smoke_run_suffix() -> str:
    configured = os.getenv("MYRM_SMOKE_RUN_ID")
    if configured:
        return configured
    return uuid.uuid4().hex[:10]


def _smoke_headers() -> dict[str, str]:
    api_key = os.getenv("MYRM_SMOKE_API_KEY") or os.getenv("SANDBOX_API_KEY")
    if not api_key:
        return {}
    return {
        "Authorization": f"Bearer {api_key}",
        "X-Sandbox-Api-Key": api_key,
    }


def _format_health_failure(health: Mapping[str, object]) -> str:
    reason = str(health.get("reason") or "unknown")
    fix_hint = _HEALTH_FIX_HINTS.get(reason, "Check the Shared Context memory health response and runtime logs.")
    payload = json.dumps(dict(health), ensure_ascii=False, sort_keys=True)
    return (
        "Shared Context memory smoke preflight failed.\n"
        f"reason={reason}\n"
        f"fix={fix_hint}\n"
        f"health={payload}"
    )


def test_smoke_headers_are_empty_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYRM_SMOKE_API_KEY", raising=False)
    monkeypatch.delenv("SANDBOX_API_KEY", raising=False)

    assert _smoke_headers() == {}


def test_smoke_headers_include_sandbox_auth_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_SMOKE_API_KEY", "smoke-secret")
    monkeypatch.delenv("SANDBOX_API_KEY", raising=False)

    assert _smoke_headers() == {
        "Authorization": "Bearer smoke-secret",
        "X-Sandbox-Api-Key": "smoke-secret",
    }


def test_health_failure_message_includes_fix_hint() -> None:
    message = _format_health_failure(
        {
            "ready": False,
            "status": "not_configured",
            "reason": "missing_embedding_api_key",
            "api_key_configured": False,
        }
    )

    assert "Shared Context memory smoke preflight failed" in message
    assert "reason=missing_embedding_api_key" in message
    assert "Configure an embedding API key" in message


@dataclass(frozen=True)
class _SmokeClient:
    client: httpx.Client
    created_context_id: str | None = None

    def with_context(self, context_id: str) -> Self:
        return type(self)(client=self.client, created_context_id=context_id)

    def get_json(self, path: str) -> dict[str, object]:
        response = self.client.get(path)
        response.raise_for_status()
        return response.json()

    def post_json(self, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        response = self.client.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    def delete(self, path: str) -> None:
        response = self.client.delete(path)
        response.raise_for_status()

    def delete_optional(self, path: str) -> None:
        response = self.client.delete(path)
        if response.status_code in (200, 204, 404):
            return
        response.raise_for_status()


@pytest.mark.skipif(
    not _BASE_URL,
    reason="Set MYRM_SMOKE_BASE_URL, for example http://localhost:8080/api/v1, to run the live Shared Context smoke.",
)
def test_live_shared_context_memory_smoke() -> None:
    assert _BASE_URL is not None
    base_url = _BASE_URL.rstrip("/")
    unique_suffix = _smoke_run_suffix()

    with httpx.Client(base_url=base_url, headers=_smoke_headers(), timeout=30.0) as raw_client:
        smoke = _SmokeClient(raw_client)
        health = smoke.get_json("/memory/shared-contexts/health/memory?probe=true")
        assert health["ready"] is True, _format_health_failure(health)

        created = smoke.post_json(
            "/memory/shared-contexts/",
            {
                "name": f"Smoke Shared Context {unique_suffix}",
                "description": "Automated Shared Context memory smoke validation.",
            },
        )
        context_id = str(created["id"])
        smoke = smoke.with_context(context_id)

        try:
            smoke.post_json(
                f"/memory/shared-contexts/{context_id}/bindings",
                {"target_type": "agent", "target_id": f"smoke-agent-{unique_suffix}"},
            )
            proposal = smoke.post_json(
                f"/memory/shared-contexts/{context_id}/proposals",
                {
                    "memory_type": "semantic",
                    "content": f"Smoke validation memory for {unique_suffix}.",
                    "source_type": "smoke",
                },
            )
            approved = smoke.post_json(f"/memory/shared-contexts/proposals/{proposal['id']}/approve")
            assert approved["status"] == "approved"
        finally:
            if smoke.created_context_id is not None:
                smoke.delete(f"/memory/shared-contexts/{smoke.created_context_id}")


@pytest.mark.skipif(
    not _BASE_URL or not _CHAT_RECALL_ENABLED,
    reason=(
        "Set MYRM_SMOKE_BASE_URL and MYRM_SMOKE_ENABLE_CHAT_RECALL=1 to run the live "
        "Shared Context chat binding + proposal governance smoke (no LLM stream)."
    ),
)
def test_live_shared_context_chat_recall_smoke() -> None:
    """Live path: conversation+agent bindings, semantic proposal, approve (product governance only).

    LLM ``agent-stream`` + ``memory_recall`` citation checks are intentionally not part of this
    file: they are provider- and latency-sensitive; use focused integration tests or manual UI runs.
    """
    assert _BASE_URL is not None
    base_url = _BASE_URL.rstrip("/")
    unique_suffix = _smoke_run_suffix()
    chat_id = f"smoke-chat-{unique_suffix}"
    message_id = f"smoke-message-{unique_suffix}"
    agent_id = f"smoke-agent-{unique_suffix}"
    unique_fact = f"citrine meadow shared recall {unique_suffix}"

    with httpx.Client(base_url=base_url, headers=_smoke_headers(), timeout=60.0) as raw_client:
        smoke = _SmokeClient(raw_client)
        health = smoke.get_json("/memory/shared-contexts/health/memory?probe=true")
        assert health["ready"] is True, _format_health_failure(health)

        created = smoke.post_json(
            "/memory/shared-contexts/",
            {
                "name": f"Smoke Chat Recall Context {unique_suffix}",
                "description": "Automated Shared Context chat binding and approval validation.",
            },
        )
        context_id = str(created["id"])
        smoke = smoke.with_context(context_id)

        try:
            smoke.post_json(
                f"/memory/shared-contexts/{context_id}/bindings",
                {"target_type": "conversation", "target_id": chat_id},
            )
            smoke.post_json(
                f"/memory/shared-contexts/{context_id}/bindings",
                {"target_type": "agent", "target_id": agent_id},
            )
            conv_bindings = smoke.get_json(
                f"/memory/shared-contexts/bindings/targets/conversation/{chat_id}"
            )
            agent_bindings = smoke.get_json(
                f"/memory/shared-contexts/bindings/targets/agent/{agent_id}"
            )
            assert int(conv_bindings.get("total", 0)) >= 1, conv_bindings
            assert int(agent_bindings.get("total", 0)) >= 1, agent_bindings
            proposal = smoke.post_json(
                f"/memory/shared-contexts/{context_id}/proposals",
                {
                    "memory_type": "semantic",
                    "content": (
                        f"Important Shared Context validation fact: {unique_fact}. "
                        f"When asked about the smoke shared recall phrase, answer {unique_fact}. "
                        f"This approved Shared Context memory is uniquely identified by {unique_fact}."
                    ),
                    "source_type": "smoke_chat_recall",
                    "source_id": message_id,
                },
            )
            approved = smoke.post_json(f"/memory/shared-contexts/proposals/{proposal['id']}/approve")
            assert approved["status"] == "approved"
        finally:
            smoke.delete_optional(f"/chats/{chat_id}")
            if smoke.created_context_id is not None:
                smoke.delete(f"/memory/shared-contexts/{smoke.created_context_id}")
