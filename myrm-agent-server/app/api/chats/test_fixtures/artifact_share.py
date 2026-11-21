"""Local-only artifact share Chrome E2E seed route.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.core.artifacts::LocalArtifactProcessor (POS: registers workspace files as artifacts, as a chat run does)
app.services.agent.params.workspace_resolve::resolve_default_chat_workspace_dir (POS: the chat's sandbox workspace, where a run writes its files)
app.services.agent.agent_service::AgentService (POS: agent list, first agent bound to the seed chat)
app.services.chat.chat_service::ChatService (POS: chat persistence)
myrm_agent_harness.core.context_vars::workspace_root_var (POS: root bound to the active run)

[OUTPUT]
seed_artifact_share_fixture: a chat that owns two registered artifacts, a Chart.js page and a Markdown report with hostile markup

[POS]
Mounted via test_fixtures/__init__.py router include. The files are registered under the chat's workspace root, the root
a share link later reads them from.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.core.context_vars import workspace_root_var

from app.config.deploy_mode import is_local_mode
from app.core.artifacts import LocalArtifactProcessor
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.agent.params.workspace_resolve import resolve_default_chat_workspace_dir
from app.services.chat.chat_service import ChatService

router = APIRouter()

_CHART_NAME = "chart.html"
_REPORT_NAME = "report.md"

# Loads Chart.js from a CDN the preview allows and draws without animation, so one frame of canvas pixels proves the script ran.
_CHART_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Share chart</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script></head>
<body><canvas id="chart" width="320" height="160"></canvas>
<script>
new Chart(document.getElementById('chart'), {
  type: 'bar',
  data: { labels: ['A', 'B', 'C'], datasets: [{ data: [3, 5, 2], backgroundColor: '#c0392b' }] },
  options: { animation: false, responsive: false },
});
</script></body></html>
"""

# Markdown whose raw HTML, event handler and script link would run if the page rendered them as markup.
_REPORT = """# Quarterly report

Plain text with **bold** words.

<script>window.__shareProbe = 'script'</script>

<img src="x" onerror="window.__shareProbe = 'onerror'">

[open the dashboard](javascript:window.__shareProbe='link')

| quarter | revenue |
| --- | --- |
| Q1 | 10 |
"""


@router.post("/test/seed-artifact-share-fixture", include_in_schema=False)
async def seed_artifact_share_fixture() -> dict[str, str]:
    """Local dev/test only: register a chart page and a hostile Markdown report as artifacts of a fresh chat."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(status_code=500, detail="No agents available for artifact share E2E seed")

    chat_id = f"e2eartshare{uuid4().hex[:8]}"
    await ChatService.create_or_update_chat(
        ChatCreate(chat_id=chat_id, title="Artifact share Chrome E2E", agent_id=agents[0].id, messages=[]),
    )
    workspace = await resolve_default_chat_workspace_dir(chat_id, persist_workspace=True)
    if not workspace:
        raise HTTPException(status_code=500, detail="Failed to resolve workspace for artifact share E2E seed")

    # One folder per artifact: the files next to an entry file ship with it, so a shared folder would mix the two pages.
    paths: dict[str, Path] = {}
    for name, content in ((_CHART_NAME, _CHART_PAGE), (_REPORT_NAME, _REPORT)):
        folder = Path(workspace) / Path(name).stem
        folder.mkdir(parents=True, exist_ok=True)
        paths[name] = folder / name
        paths[name].write_text(content, encoding="utf-8")

    event: dict[str, object] = {
        "type": "artifacts_ready",
        "data": [{"filename": name, "path": str(path)} for name, path in paths.items()],
    }
    bound_root = workspace_root_var.set(workspace)
    try:
        emitted = await LocalArtifactProcessor(chat_id=chat_id).process_artifacts_ready(event)
    finally:
        workspace_root_var.reset(bound_root)
    rows = cast(list[dict[str, object]], emitted["data"]) if emitted else []
    ids = {str(row["filename"]): str(row["id"]) for row in rows}
    if set(ids) != set(paths):
        raise HTTPException(status_code=500, detail="Artifact share E2E seed could not register its files")
    return {"chat_id": chat_id, "chart_artifact_id": ids[_CHART_NAME], "report_artifact_id": ids[_REPORT_NAME]}
