"""Real-model agent turn in a chat workspace that also holds the files of a hostile repository.

[INPUT]
- POST /api/v1/agents/agent-stream with the LITE model (POS: the whole server path, a real provider call, SSE back)
- The harness workspace of the chat (POS: where rule files are read from; also holds a FIFO ``SKILL.md`` and sparse config files)

[OUTPUT]
- Fails when the stream reports an error event, when the turn does not finish, or when the model does not answer with the
  codeword that only the folder's ``AGENTS.md`` states.

[POS]
Pins that a rule file next to those files still reaches the model through the system prompt and that the answer streams back.
The blocking read itself is pinned on the folder preview (``tests/api/security/test_workspace_trust_hostile_folder_api.py``);
this turn also passes on a source without the bounded reads, so it checks rule delivery and is not the guard for the read.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.code_execution import create_workspace_service

from app.config.settings import get_settings
from app.platform_utils.workspace_session import to_workspace_session_id
from tests.api.agent.test_workspace_rules_e2e import perform_agent_stream
from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection

SPARSE_BYTES = 64 * 1024 * 1024
CODEWORD = "KRAKATOA-7731"

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(sys.platform == "win32", reason="FIFOs and sparse files are POSIX"),
    pytest.mark.skipif(not os.environ.get("LITE_API_KEY"), reason="E2E test requires LITE_API_KEY"),
    # A blocked read stalls the turn inside the event loop; the thread method ends the run with a stack dump.
    pytest.mark.timeout(240, method="thread"),
]


async def _harness_workspace(chat_id: str) -> Path:
    workspace_service = create_workspace_service(root_dir=Path(get_settings().database.harness_dir))
    workspace = await workspace_service.get_or_create(session_id=to_workspace_session_id(chat_id))
    path = Path(workspace_service.get_workspace_absolute_path(workspace))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _plant_hostile_files(workspace: Path) -> None:
    (workspace / "AGENTS.md").write_text(
        f"Project Convention: the project codeword is {CODEWORD}. When the user asks for the project codeword, "
        "answer with exactly that word.\n",
        encoding="utf-8",
    )
    honest = workspace / "skills" / "honest"
    honest.mkdir(parents=True)
    (honest / "SKILL.md").write_text(
        "---\nname: honest\ndescription: A skill the folder really ships.\n---\n\nBody.\n", encoding="utf-8"
    )
    hostile = workspace / "skills" / "hostile"
    hostile.mkdir()
    os.mkfifo(hostile / "SKILL.md")
    (workspace / ".myrm").mkdir()
    for sparse in (workspace / "mcp.json", workspace / ".myrm" / "config.toml"):
        with sparse.open("wb") as handle:
            handle.truncate(SPARSE_BYTES)


@pytest.mark.asyncio
async def test_the_codeword_of_the_rule_file_comes_back_through_a_real_model_turn(client: TestClient) -> None:
    chat_id = f"whostile-{uuid.uuid4().hex[:10]}"
    assert client.post("/api/v1/chats/", json={"chat_id": chat_id}).status_code == 200
    _plant_hostile_files(await _harness_workspace(chat_id))

    answer, collected, _ = perform_agent_stream(
        client,
        "What is the project codeword? Answer with the codeword only.",
        chat_id,
        model_selection=get_lite_model_selection(),
    )

    check_e2e_errors(collected)
    assert CODEWORD in answer.upper()
