"""Real-model check that of the rule files of a trusted folder only the first match reaches the agent.

[INPUT]
- A folder the user links to a project, previews and trusts through the project and folder-trust API (POS: the workspace root of the turn)
- POST /api/v1/agents/agent-stream with the LITE model (POS: the whole server path, a real provider call, SSE back)
- The messages ChatLiteLLM sends to the provider (POS: recorded where they are built)

[OUTPUT]
- Fails when the request of the turn lacks the codeword of ``AGENTS.md`` or holds the one of ``.cursorrules``, or when the model's answer does not
  follow the same two.

[POS]
The rules of a folder nobody trusted stay out of the request, so the rule files sit in a folder the user trusted. The request is what the server
decides; the answer also depends on the model following what it was given.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.support.real_model_workspace_turns import TURN_TIMEOUT_SECONDS, ask, main_request_text, trusted_project_folder

HIGH_PRIORITY_CODEWORD = "WUBBALUBBADUBDUB"
LOW_PRIORITY_CODEWORD = "BAZINGA"
PROMPT = "Do not use any tools. Write a simple python script that prints hello world. Answer with the code only."

pytestmark = [
    pytest.mark.usefixtures("routes_and_trust", "stuck_turn_report"),
    pytest.mark.e2e,
    pytest.mark.skipif(not os.environ.get("LITE_API_KEY"), reason="E2E test requires LITE_API_KEY"),
    pytest.mark.timeout(TURN_TIMEOUT_SECONDS, method="thread"),
]


def _rule(codeword: str) -> str:
    return f"Project Convention: When writing any code, you MUST include the comment '# {codeword}' at the top."


def test_first_match_wins_agents_md_over_cursorrules(
    client: TestClient, sent: list[list[dict[str, object]]], tmp_path: Path
) -> None:
    folder = tmp_path / "linked"
    folder.mkdir()
    (folder / ".cursorrules").write_text(_rule(LOW_PRIORITY_CODEWORD), encoding="utf-8")
    (folder / "AGENTS.md").write_text(_rule(HIGH_PRIORITY_CODEWORD), encoding="utf-8")

    # Rule adherence depends on the model's instruction-following ability; the default BASIC_MODEL (agnes flash)
    # is too weak to reliably honor injected rules, so this E2E uses the stronger LITE_MODEL.
    with trusted_project_folder(client, folder) as chat_id:
        answer = ask(client, chat_id, PROMPT)

    request = main_request_text(sent, PROMPT).upper()
    assert request, "the question of the turn never reached a provider"
    assert HIGH_PRIORITY_CODEWORD in request
    assert LOW_PRIORITY_CODEWORD not in request
    assert HIGH_PRIORITY_CODEWORD in answer
    assert LOW_PRIORITY_CODEWORD not in answer
