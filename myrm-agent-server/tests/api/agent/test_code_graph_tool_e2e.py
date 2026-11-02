"""Real-model check that ``code_graph_tool`` answers a ``callers`` question with the letter case that was asked.

[INPUT]
- A folder with Python files that the user links to a project, previews and trusts (POS: the workspace root of the turn)
- The preset skill ``repo-call-graph`` switched on through the skills config API (POS: what mounts ``code_graph_tool``)
- POST /api/v1/agents/agent-stream with the LITE model (POS: the whole server path, a real provider call, SSE back)

[OUTPUT]
- Fails when the model never calls ``code_graph_tool`` with the action ``callers``, or when the tool's rows hold a call
  spelt with another letter case

[POS]
Server pytest-only. The tool results are recorded by wrapping the mounted navigator, so they are what the real turn computed.
The streamed answer is not asserted: it carries the model's own narration, which may name lines it read for itself.
Whether the model asks for ``callers`` at all depends on it following the question.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.runtime.paths.execution_paths import PERSISTENT_ROOT_ENV

from app.api.skills import router as skills_router
from app.services.code_graph import agent_tool
from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection
from tests.support.real_model_workspace_turns import TURN_TIMEOUT_SECONDS, perform_agent_stream, trusted_project_folder

pytestmark = [
    pytest.mark.usefixtures("routes_and_trust", "stuck_turn_report"),
    pytest.mark.e2e,
    pytest.mark.skipif(not os.environ.get("LITE_API_KEY"), reason="E2E test requires LITE_API_KEY"),
    pytest.mark.timeout(TURN_TIMEOUT_SECONDS, method="thread"),
]

SKILL_ID = "repo-call-graph"
PROMPT = (
    "Use the code_graph_tool with the action callers and the query select (all lowercase) to find who calls the "
    "function select in this project. Answer with one file:line per call site and nothing else."
)
CORE_PY = "def select(items):\n    return items[0]\n\n\nclass Select:\n    pass\n"
# Line 5 calls select, line 6 calls db.select, line 7 calls db.Select: the same name spelt with another letter case.
APP_PY = (
    "from core import Select, select\n\n\ndef run(items, db):\n    first = select(items)\n    db.select(items)\n"
    "    db.Select(items)\n    return first, Select()\n"
)


@pytest.fixture(autouse=True)
def isolated_persistent_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The index database lives under the persistent root, whose default ``/persistent`` is not writable on a dev machine."""
    monkeypatch.setenv(PERSISTENT_ROOT_ENV, str(tmp_path / "persistent"))


@pytest.fixture
def skill_enabled(app: FastAPI, client: TestClient) -> None:
    app.include_router(skills_router, prefix="/api/v1/skills")
    enabled = client.put("/api/v1/skills/config", json={"enabled_prebuilt_ids": [SKILL_ID]})
    assert enabled.status_code == 200, enabled.text
    assert SKILL_ID in enabled.json()["enabled_prebuilt_ids"], enabled.text


@pytest.fixture
def tool_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict[str, object]]]:
    """Every ``(action, query, result)`` the mounted navigator answered, recorded around the real implementation."""
    recorded: list[tuple[str, str, dict[str, object]]] = []
    real_ask = agent_tool._Navigator.ask

    async def recording_ask(self: agent_tool._Navigator, action: agent_tool.CodeGraphAction, query: str) -> dict[str, object]:
        result = await real_ask(self, action, query)
        recorded.append((action, query, result))
        return result

    monkeypatch.setattr(agent_tool._Navigator, "ask", recording_ask)
    return recorded


def test_callers_answer_keeps_the_letter_case_that_was_asked(
    client: TestClient, skill_enabled: None, tool_calls: list[tuple[str, str, dict[str, object]]], tmp_path: Path
) -> None:
    folder = tmp_path / "linked"
    folder.mkdir()
    (folder / "core.py").write_text(CORE_PY, encoding="utf-8")
    (folder / "app.py").write_text(APP_PY, encoding="utf-8")

    with trusted_project_folder(client, folder) as chat_id:
        _, collected, _ = perform_agent_stream(client, PROMPT, chat_id, model_selection=get_lite_model_selection())

    check_e2e_errors(collected)
    asked = [result for action, query, result in tool_calls if (action, query) == ("callers", "select")]
    assert asked, f"the model never asked callers for select: {[(a, q) for a, q, _ in tool_calls]}"
    for result in asked:
        metadata = result["metadata"]
        assert isinstance(metadata, dict) and not metadata.get("error"), result
        rows = json.loads(str(result["content"]))["rows"]
        assert {row["callee"] for row in rows} == {"select", "db.select"}, rows
        assert {row["at"] for row in rows} == {"app.py:5", "app.py:6"}, rows
