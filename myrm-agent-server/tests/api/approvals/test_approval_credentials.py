"""One-time credentials staged from a tool approval card reach the approved command, and only it.

The chain is exercised with the real pieces on both sides: the harness builds the approval payload of a bash call,
the endpoint stages credentials for the command that payload shows, and a real bash executor, running under the
session key the agent's run context carries, is the one that must deliver them.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.meta_tools.bash._executor.prepare_mixin import BashExecutorPrepareMixin
from myrm_agent_harness.agent.middlewares.approval._interrupt_payload import build_interrupt_payload
from myrm_agent_harness.api import command_digest, get_ephemeral_credential_store
from myrm_agent_harness.core.context_vars import approval_session_var
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext
from myrm_agent_harness.toolkits.code_execution.security.archive_sanitizer import sanitize_archive_command
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents.general_agent import GeneralAgent
from app.core.types import ModelConfig
from app.services.agent.params.workspace_resolve import chat_session_id

CHAT_ID = "chat-cred-1"
SECRET = "ProductionSuperSecret999!"
# A delivered credential is masked in anything the command prints, so the command prints it as hex.
COMMAND = "printenv DB_PASSWORD | tr -d '\\n' | od -An -tx1 | tr -d ' \\n' | grep . || echo NONE"
SECRET_AS_HEX = SECRET.encode().hex()


@pytest.fixture(autouse=True)
def clean_store() -> Iterator[None]:
    store = get_ephemeral_credential_store()
    yield
    store.purge_session(chat_session_id(CHAT_ID))
    store.purge_session(chat_session_id("chat-cred-other"))


def _stage(client: TestClient, command: str = COMMAND, chat_id: str = CHAT_ID, **overrides: object) -> dict:
    body: dict[str, object] = {
        "chat_id": chat_id,
        "command": command,
        "credentials": [{"key": "DB_PASSWORD", "secret": SECRET, **overrides}],
    }
    resp = client.post("/api/v1/approvals/credentials", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestStaging:
    def test_credential_is_staged_for_the_command_digest_in_the_run_session(self, client: TestClient) -> None:
        data = _stage(client, ttl_seconds=45.0)

        assert SECRET not in str(data)
        (item,) = data["staged"]
        assert item["handle_id"].startswith("cred_ephemeral_")
        assert item["key"] == "DB_PASSWORD"
        summary = get_ephemeral_credential_store().peek_summary(chat_session_id(CHAT_ID), item["handle_id"])
        assert summary is not None
        assert summary.expected_action_digest == command_digest(COMMAND)
        assert summary.ttl_seconds == 45.0
        assert not summary.is_consumed

    def test_the_session_key_is_the_one_the_agent_run_context_carries(self) -> None:
        agent = GeneralAgent(
            model_cfg=ModelConfig(provider="openai", model="gpt-4o-mini", api_key="test"),
            mcp_config=None,
            search_service_cfg=SearchServiceConfig(search_service="searxng"),
            chat_id=CHAT_ID,
            channel_name="web_chat",
            agent_id="planner",
        )

        context = agent._build_runtime_context(query="x", chat_history=[], effective_chat_id=CHAT_ID)

        assert context["session_id"] == chat_session_id(CHAT_ID)

    @pytest.mark.parametrize("key", ["LD_PRELOAD", "BASH_ENV", "PATH", "1BAD", "GIT_EXTERNAL_DIFF", "RUBYOPT", "LD_ANYTHING"])
    def test_a_key_that_could_hijack_the_shell_is_refused_and_nothing_is_staged(self, client: TestClient, key: str) -> None:
        resp = client.post(
            "/api/v1/approvals/credentials",
            json={
                "chat_id": CHAT_ID,
                "command": COMMAND,
                "credentials": [
                    {"key": "DB_PASSWORD", "secret": "one"},
                    {"key": key, "secret": "/evil.so"},
                ],
            },
        )

        assert resp.status_code == 400
        assert get_ephemeral_credential_store().list_summaries(chat_session_id(CHAT_ID)) == []

    @pytest.mark.parametrize(
        "patch_body",
        [
            {"command": "   "},
            {"command": ""},
            {"chat_id": ""},
            {"credentials": []},
            {"credentials": [{"key": "DB_PASSWORD", "secret": ""}]},
            {"credentials": [{"key": "DB_PASSWORD", "secret": "x", "ttl_seconds": 0}]},
            {"credentials": [{"key": "DB_PASSWORD", "secret": "x", "ttl_seconds": 100000}]},
        ],
    )
    def test_malformed_requests_are_rejected(self, client: TestClient, patch_body: dict[str, object]) -> None:
        body: dict[str, object] = {
            "chat_id": CHAT_ID,
            "command": COMMAND,
            "credentials": [{"key": "DB_PASSWORD", "secret": "x"}],
        }
        body.update(patch_body)

        resp = client.post("/api/v1/approvals/credentials", json=body)

        assert resp.status_code in (400, 422)
        assert get_ephemeral_credential_store().list_summaries(chat_session_id(CHAT_ID)) == []


class TestWipe:
    def test_wipe_zeroizes_only_the_requested_handles_of_that_chat(self, client: TestClient) -> None:
        mine = _stage(client)["staged"][0]["handle_id"]
        other = _stage(client, chat_id="chat-cred-other")["staged"][0]["handle_id"]

        resp = client.post("/api/v1/approvals/credentials/wipe", json={"chat_id": CHAT_ID, "handle_ids": [mine, other]})

        assert resp.status_code == 200
        assert resp.json() == {"wiped": 1}
        store = get_ephemeral_credential_store()
        assert store.list_summaries(chat_session_id(CHAT_ID)) == []
        assert [s.handle_id for s in store.list_summaries(chat_session_id("chat-cred-other"))] == [other]


@pytest.mark.skipif(sys.platform == "win32", reason="drives a real bash shell")
class TestEndToEnd:
    """The approval card shows one text; the executor receives a prepared script made from it."""

    @pytest.fixture
    async def executor(self, tmp_path: Path) -> AsyncIterator[LocalExecutor]:
        local = LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path))
        try:
            yield local
        finally:
            await local.close()

    @staticmethod
    def _approved_command() -> str:
        call = {"name": "bash_code_execute_tool", "id": "call_1", "args": {"command": COMMAND}}
        payload, _ = build_interrupt_payload([(0, call, "shell_exec", "needs approval", None)], CHAT_ID)
        return str(payload["actionRequests"][0]["args"]["command"])

    @staticmethod
    async def _run(executor: LocalExecutor, tmp_path: Path, issued: str) -> str:
        prepared = BashExecutorPrepareMixin()._inject_resilience_script(sanitize_archive_command(issued))
        token = approval_session_var.set(chat_session_id(CHAT_ID))
        try:
            result = await executor.execute_bash(
                ExecutionContext(
                    code=prepared,
                    original_code=issued,
                    session_id=chat_session_id(CHAT_ID),
                    work_dir=str(tmp_path),
                    workspace_root=str(tmp_path),
                    timeout=30,
                )
            )
        finally:
            approval_session_var.reset(token)
        assert result.success, result.error
        return result.stdout.strip()

    async def test_the_approved_command_reads_the_credential_once(
        self, client: TestClient, executor: LocalExecutor, tmp_path: Path
    ) -> None:
        approved = self._approved_command()
        _stage(client, command=approved)

        assert await self._run(executor, tmp_path, approved) == SECRET_AS_HEX
        assert await self._run(executor, tmp_path, approved) == "NONE"

    async def test_a_command_the_user_edited_after_staging_reads_nothing(
        self, client: TestClient, executor: LocalExecutor, tmp_path: Path
    ) -> None:
        approved = self._approved_command()
        _stage(client, command=approved)

        assert await self._run(executor, tmp_path, f"{approved} # edited") == "NONE"
        assert len(get_ephemeral_credential_store().list_summaries(chat_session_id(CHAT_ID))) == 1

    async def test_another_chat_cannot_read_it(self, client: TestClient, executor: LocalExecutor, tmp_path: Path) -> None:
        approved = self._approved_command()
        _stage(client, command=approved, chat_id="chat-cred-other")

        assert await self._run(executor, tmp_path, approved) == "NONE"
