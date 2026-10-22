"""
[INPUT]: Event-driven causality lineage events (trigger, rule, agent actions, artifact diffs) and reverse lookup queries.
[OUTPUT]: Pydantic schemas and REST endpoints for event-driven causality lineage tracking and reverse file attribution.
[POS]: myrm-agent/myrm-agent-server/app/api/system/event_causality_lineage_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.event_causality_lineage import (
    AgentActionNode,
    ArtifactChangeRecord,
    CausalityLineageRecord,
    CausalityRuleMatch,
    ExternalEventTrigger,
    FileAttributionResult,
    get_default_event_causality_tracker,
)

router = APIRouter(prefix="/event-causality", tags=["event-causality"])


# --- Pydantic Request & Response Schemas ---


class ExternalEventTriggerModel(BaseModel):
    event_id: str = Field(..., description="Unique external event identifier")
    source_type: str = Field(..., description="Event origin: github_webhook, slack_mention, mcp_event, cron")
    event_name: str = Field(..., description="Canonical event name (e.g. issues.opened)")
    payload_summary: str = Field(..., description="Concise summary of trigger payload")
    received_at_ms: int = Field(default=0, description="Timestamp when event was ingested")


class CausalityRuleMatchModel(BaseModel):
    rule_id: str = Field(..., description="Matched automation rule identifier")
    rule_name: str = Field(..., description="Rule human-readable title")
    matched_condition: str = Field(..., description="Condition expression that evaluated to true")


class AgentActionNodeModel(BaseModel):
    action_id: str = Field(..., description="Action node identifier")
    agent_role: str = Field(..., description="Specialized agent persona or title")
    decision_rationale: str = Field(..., description="Explanation of why this action was taken")
    tool_name: str = Field(..., description="Tool or routine invoked")
    input_summary: str = Field(..., description="Tool parameters summary")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Execution latency in milliseconds")
    tokens_consumed: int = Field(default=0, ge=0, description="Tokens consumed during this step")
    timestamp_ms: int = Field(default=0, description="Action timestamp")


class ArtifactChangeRecordModel(BaseModel):
    file_path: str = Field(..., description="Workspace relative or absolute file path")
    change_type: str = Field(..., description="created, modified, deleted")
    diff_summary: str = Field(..., description="Summary of textual or semantic patch diff")
    commit_sha: str = Field(default="", description="Associated Git commit SHA if committed")
    timestamp_ms: int = Field(default=0, description="Change timestamp")


class RecordLineageRequest(BaseModel):
    causality_trace_id: str = Field(..., description="Unique causality trace DAG identifier")
    session_id: str = Field(..., description="Parent agent session ID")
    trigger: ExternalEventTriggerModel
    rule: CausalityRuleMatchModel
    agent_role: str = Field(..., description="Primary agent role executing the workflow")
    actions: List[AgentActionNodeModel] = Field(default_factory=list, description="Ordered cognitive action steps")
    artifacts: List[ArtifactChangeRecordModel] = Field(default_factory=list, description="Affected file artifacts")


class CausalityLineageRecordModel(BaseModel):
    causality_trace_id: str
    session_id: str
    trigger: ExternalEventTriggerModel
    rule: CausalityRuleMatchModel
    agent_role: str
    actions: List[AgentActionNodeModel]
    artifacts: List[ArtifactChangeRecordModel]
    total_tokens: int
    total_duration_ms: float
    created_at_ms: int


class FileAttributionResultModel(BaseModel):
    file_path: str
    causality_trace_id: str
    trigger_event_id: str
    source_type: str
    event_name: str
    agent_role: str
    change_record: ArtifactChangeRecordModel
    rationale: str
    occurred_at_ms: int


# --- Helper Converters ---


def _to_lineage_model(rec: CausalityLineageRecord) -> CausalityLineageRecordModel:
    return CausalityLineageRecordModel(
        causality_trace_id=rec.causality_trace_id,
        session_id=rec.session_id,
        trigger=ExternalEventTriggerModel(
            event_id=rec.trigger.event_id,
            source_type=rec.trigger.source_type,
            event_name=rec.trigger.event_name,
            payload_summary=rec.trigger.payload_summary,
            received_at_ms=rec.trigger.received_at_ms,
        ),
        rule=CausalityRuleMatchModel(
            rule_id=rec.rule.rule_id,
            rule_name=rec.rule.rule_name,
            matched_condition=rec.rule.matched_condition,
        ),
        agent_role=rec.agent_role,
        actions=[
            AgentActionNodeModel(
                action_id=a.action_id,
                agent_role=a.agent_role,
                decision_rationale=a.decision_rationale,
                tool_name=a.tool_name,
                input_summary=a.input_summary,
                duration_ms=a.duration_ms,
                tokens_consumed=a.tokens_consumed,
                timestamp_ms=a.timestamp_ms,
            )
            for a in rec.actions
        ],
        artifacts=[
            ArtifactChangeRecordModel(
                file_path=art.file_path,
                change_type=art.change_type,
                diff_summary=art.diff_summary,
                commit_sha=art.commit_sha,
                timestamp_ms=art.timestamp_ms,
            )
            for art in rec.artifacts
        ],
        total_tokens=rec.total_tokens,
        total_duration_ms=rec.total_duration_ms,
        created_at_ms=rec.created_at_ms,
    )


def _to_attribution_model(attr: FileAttributionResult) -> FileAttributionResultModel:
    return FileAttributionResultModel(
        file_path=attr.file_path,
        causality_trace_id=attr.causality_trace_id,
        trigger_event_id=attr.trigger_event_id,
        source_type=attr.source_type,
        event_name=attr.event_name,
        agent_role=attr.agent_role,
        change_record=ArtifactChangeRecordModel(
            file_path=attr.change_record.file_path,
            change_type=attr.change_record.change_type,
            diff_summary=attr.change_record.diff_summary,
            commit_sha=attr.change_record.commit_sha,
            timestamp_ms=attr.change_record.timestamp_ms,
        ),
        rationale=attr.rationale,
        occurred_at_ms=attr.occurred_at_ms,
    )


# --- Endpoints ---


@router.post("/record", response_model=CausalityLineageRecordModel)
async def record_causality_lineage(req: RecordLineageRequest) -> CausalityLineageRecordModel:
    """Record an end-to-end event-driven causality lineage DAG and update reverse indexes."""
    tracker = get_default_event_causality_tracker()

    trigger = ExternalEventTrigger(
        event_id=req.trigger.event_id,
        source_type=req.trigger.source_type,
        event_name=req.trigger.event_name,
        payload_summary=req.trigger.payload_summary,
        received_at_ms=req.trigger.received_at_ms,
    )

    rule = CausalityRuleMatch(
        rule_id=req.rule.rule_id,
        rule_name=req.rule.rule_name,
        matched_condition=req.rule.matched_condition,
    )

    actions = [
        AgentActionNode(
            action_id=a.action_id,
            agent_role=a.agent_role,
            decision_rationale=a.decision_rationale,
            tool_name=a.tool_name,
            input_summary=a.input_summary,
            duration_ms=a.duration_ms,
            tokens_consumed=a.tokens_consumed,
            timestamp_ms=a.timestamp_ms,
        )
        for a in req.actions
    ]

    artifacts = [
        ArtifactChangeRecord(
            file_path=art.file_path,
            change_type=art.change_type,
            diff_summary=art.diff_summary,
            commit_sha=art.commit_sha,
            timestamp_ms=art.timestamp_ms,
        )
        for art in req.artifacts
    ]

    rec = tracker.record_lineage(
        causality_trace_id=req.causality_trace_id,
        session_id=req.session_id,
        trigger=trigger,
        rule=rule,
        agent_role=req.agent_role,
        actions=actions,
        artifacts=artifacts,
    )

    return _to_lineage_model(rec)


@router.get("/lineage/{causality_trace_id}", response_model=CausalityLineageRecordModel)
async def get_causality_lineage(causality_trace_id: str) -> CausalityLineageRecordModel:
    """Fetch complete causality lineage DAG by trace ID."""
    tracker = get_default_event_causality_tracker()
    rec = tracker.get_lineage(causality_trace_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Causality lineage not found")
    return _to_lineage_model(rec)


@router.get("/lineages", response_model=List[CausalityLineageRecordModel])
async def list_causality_lineages(
    source_type: Optional[str] = Query(None, description="Filter by event source (e.g. github_webhook, cron)"),
    event_id: Optional[str] = Query(None, description="Filter by specific event ID"),
    limit: int = Query(50, ge=1, le=200, description="Max lineage records to return"),
) -> List[CausalityLineageRecordModel]:
    """Query causality lineage records."""
    tracker = get_default_event_causality_tracker()
    results = tracker.list_lineages(source_type=source_type, event_id=event_id, limit=limit)
    return [_to_lineage_model(r) for r in results]


@router.get("/reverse-lookup", response_model=List[FileAttributionResultModel])
async def reverse_lookup_file_change(
    file_path: str = Query(..., description="Target file path to trace inducing external event"),
) -> List[FileAttributionResultModel]:
    """Reverse trace all external events and agent rationales that modified a specific file."""
    tracker = get_default_event_causality_tracker()
    attributions = tracker.reverse_lookup_file(file_path=file_path)
    return [_to_attribution_model(a) for a in attributions]


@router.post("/reset")
async def reset_causality_tracker() -> Dict[str, bool]:
    """Reset all causality records and inverted file attribution indexes."""
    tracker = get_default_event_causality_tracker()
    tracker.reset()
    return {"ok": True}
