"""Wiki maintain REST routes: start a background run and read its status.

[INPUT]
- fastapi::APIRouter, Depends, HTTPException, Query
- app.api.dependencies::get_optional_llm_for_user (POS: optional LLM for maintain)
- app.services.wiki.maintain (POS: background maintain run + single flight per vault scope)
- app.services.wiki.health_report_service::WikiHealthIssueResponse (POS: health issue response model)

[OUTPUT]
- router: POST /maintain (202), POST /maintain/cancel and GET /maintain/status
- WikiMaintenanceResponse / WikiMaintainStatusResponse: result and status payloads

[POS]
HTTP boundary of wiki maintenance. A full run takes minutes, longer than the control-plane proxy waits for a
response, so POST only starts (or joins) the run and the Settings page follows it through the status route;
cancel asks the run to stop between model calls and keeps what it already wrote.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode
from pydantic import BaseModel, Field

from app.api.dependencies import get_optional_llm_for_user
from app.services.wiki.health_report_service import WikiHealthIssueResponse

if TYPE_CHECKING:
    from app.services.wiki.maintain import WikiMaintainRunResult
    from app.services.wiki.maintain.run_registry import MaintainRun

router = APIRouter(prefix="/maintain", tags=["wiki-maintain"])


class WikiMaintenanceResponse(BaseModel):
    issues_found: int
    issues_fixed: int
    connections_discovered: int
    duration_ms: int
    open_actions_count: int = 0
    raw_security_removed: int = 0
    raw_security_removed_paths: list[str] = Field(default_factory=list)
    issues: list[WikiHealthIssueResponse] = Field(default_factory=list)
    ai_unavailable: bool = False


class WikiMaintainStatusResponse(BaseModel):
    state: Literal["idle", "running", "succeeded", "cancelled", "failed"] = "idle"
    mode: Literal["structural", "full"] | None = None
    phase: Literal["drift_review", "link_discovery"] | None = None
    done: int = 0
    total: int = 0
    # Cancel was asked and the run is still winding down; lets a page that reloads meanwhile show it as stopping.
    cancel_requested: bool = False
    result: WikiMaintenanceResponse | None = None
    error_code: Literal["maintain_failed", "maintain_timeout", "compile_in_progress"] | None = None


def _maintenance_response(result: WikiMaintainRunResult) -> WikiMaintenanceResponse:
    return WikiMaintenanceResponse(
        issues_found=result.issues_found,
        issues_fixed=result.issues_fixed,
        connections_discovered=result.connections_discovered,
        duration_ms=result.duration_ms,
        open_actions_count=result.open_actions_count,
        raw_security_removed=result.raw_security_removed,
        raw_security_removed_paths=list(result.raw_security_removed_paths),
        ai_unavailable=result.ai_unavailable,
        issues=[
            WikiHealthIssueResponse(
                issue_type=str(item["issue_type"]),
                severity=str(item["severity"]),
                location=str(item["location"]),
                description=str(item["description"]),
                action_kind=str(item["action_kind"]),
                suggested_fix=(str(item["suggested_fix"]) if item.get("suggested_fix") is not None else None),
            )
            for item in result.lint_issues
        ],
    )


def _status_response(run: MaintainRun | None) -> WikiMaintainStatusResponse:
    if run is None:
        return WikiMaintainStatusResponse()
    return WikiMaintainStatusResponse(
        state=run.state.value,
        mode=run.mode,
        phase=run.phase.value if run.phase is not None else None,
        done=run.done,
        total=run.total,
        cancel_requested=run.cancel_requested,
        result=_maintenance_response(run.result) if run.result is not None else None,
        error_code=run.error_code,
    )


@router.post("", response_model=WikiMaintainStatusResponse, status_code=202)
async def maintain_wiki(
    llm: Annotated[BaseChatModel, Depends(get_optional_llm_for_user)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
    mode: Annotated[
        Literal["structural", "full"],
        Query(description="Maintenance intensity: structural (default) or full"),
    ] = "structural",
) -> WikiMaintainStatusResponse:
    """Start a maintenance run in the background, or join the run already in flight for this vault."""
    from app.services.wiki.maintain import schedule_wiki_maintain

    scheduled = schedule_wiki_maintain(
        llm=llm,
        agent_id=agent_id,
        mode=MaintainMode.FULL if mode == "full" else MaintainMode.STRUCTURAL,
    )
    if scheduled.skipped_reason == "compile_in_progress":
        raise HTTPException(status_code=409, detail="Wiki compilation is in progress; maintain skipped")
    return _status_response(scheduled.run)


@router.post("/cancel", response_model=WikiMaintainStatusResponse)
async def cancel_maintain_run(
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiMaintainStatusResponse:
    """Ask the run in flight to stop; its status is returned either way, so calling again changes nothing."""
    from app.services.wiki.maintain import cancel_wiki_maintain

    return _status_response(cancel_wiki_maintain(agent_id))


@router.get("/status", response_model=WikiMaintainStatusResponse)
async def get_wiki_maintain_status(
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> WikiMaintainStatusResponse:
    """Progress of the latest maintenance run of this vault, with its result once it has finished."""
    from app.services.wiki.maintain import get_wiki_maintain_run

    return _status_response(get_wiki_maintain_run(agent_id))
