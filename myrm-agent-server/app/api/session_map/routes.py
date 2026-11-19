"""
[INPUT]
- SessionNodeModel, ProjectClusterModel, FleetCockpitSummary, SessionSearchRequest, SessionSearchResponse from .models
- Project, Chat and ApprovalRecord rows read through the request's AsyncSession
- AgentGateway.active_session_ids() for the turns currently in flight

[OUTPUT]
- APIRouter exposing:
  - GET /api/v1/session-map/projects (list project clusters with internal session nodes)
  - GET /api/v1/session-map/cockpit (aggregate fleet metrics over the same session nodes)
  - POST /api/v1/session-map/search (search sessions across projects with snippet highlights)

[POS]
Backend API for Project-Centric Session Map and Agent State Cockpit View.
Every figure comes from stored rows or the live gateway; a database failure surfaces as an error response, never as
placeholder data.
Strict typing: Zero `Any`. File length < 320 lines.
"""

from collections import Counter

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.database.models.approval import ApprovalRecord
from app.database.models.chat import Chat
from app.database.models.project import Project
from app.services.agent.gateway import get_agent_gateway
from app.services.skills.growth.constants import is_background_growth_approval

from .models import (
    AgentState,
    FleetCockpitSummary,
    ProjectClusterModel,
    SessionNodeModel,
    SessionSearchHit,
    SessionSearchRequest,
    SessionSearchResponse,
)

router = APIRouter()

# The map plots the newest chats only, which bounds the payload.
_MAX_SESSIONS = 200


def _infer_session_state(chat: Chat, running_ids: frozenset[str], waiting_ids: frozenset[str]) -> AgentState:
    """Infers the agent runtime pulse of a chat.

    A chat waits exactly while an approval is pending for it and works exactly while the gateway has a turn in flight
    for it; a failing compaction streak outranks both.
    """
    if chat.compression_ineffective_streak > 3:
        return "error"
    if chat.id in waiting_ids:
        return "waiting_input"
    if chat.id in running_ids:
        return "working"
    if chat.compacted_before_id:
        return "idle"
    return "ready"


async def _chats_awaiting_decision(db: AsyncSession) -> frozenset[str]:
    """Chats with a pending approval that suspends the agent for a user decision.

    Background growth drafts are reviewed in the skills inbox and never hold a chat, the same split the approvals
    inbox and the pending-approval gate make.
    """
    rows = await db.execute(
        select(ApprovalRecord.chat_id, ApprovalRecord.action_type, ApprovalRecord.thread_id).where(
            ApprovalRecord.status == "PENDING", ApprovalRecord.chat_id.is_not(None)
        )
    )
    return frozenset(
        chat_id
        for chat_id, action_type, thread_id in rows
        if chat_id and not is_background_growth_approval(action_type, thread_id)
    )


def _build_default_cluster() -> ProjectClusterModel:
    """Bucket for the chats that belong to no project."""
    return ProjectClusterModel(
        id="proj-default",
        name="Global Workspace",
        description="Unassigned standalone agent sessions",
        workspace_path=None,
    )


def _build_session_node(chat: Chat, state: AgentState) -> SessionNodeModel:
    return SessionNodeModel(
        id=chat.id,
        title=chat.title or "Untitled Session",
        project_id=chat.project_id,
        agent_id=chat.agent_id,
        agent_name=f"Agent-{chat.agent_id[:6]}" if chat.agent_id else "Myrm-General",
        state=state,
        current_task=chat.last_message[:120] if chat.last_message else None,
        tokens_used=chat.total_tokens or 0,
        last_active_at=chat.updated_at.isoformat(),
        tags=chat.tags or [],
        workspace_dir=chat.workspace_dir,
    )


async def _load_clusters(db: AsyncSession, state_filter: AgentState | None = None) -> list[ProjectClusterModel]:
    """Project clusters with their session nodes, optionally keeping only the sessions in one runtime state."""
    projects = (await db.execute(select(Project).order_by(Project.sort_order.asc(), Project.created_at.desc()))).scalars().all()
    chats = (await db.execute(select(Chat).order_by(Chat.updated_at.desc()).limit(_MAX_SESSIONS))).scalars().all()
    waiting_ids = await _chats_awaiting_decision(db)
    running_ids = get_agent_gateway().active_session_ids()

    project_clusters = {
        p.id: ProjectClusterModel(
            id=p.id,
            name=p.name,
            description=p.description or "",
            color=p.color or "#6366f1",
            workspace_path=p.workspace_path,
        )
        for p in projects
    }
    default_cluster = _build_default_cluster()

    for chat in chats:
        state = _infer_session_state(chat, running_ids, waiting_ids)
        if state_filter and state != state_filter:
            continue

        cluster = project_clusters.get(chat.project_id) if chat.project_id else None
        if cluster is None:
            cluster = default_cluster
        node = _build_session_node(chat, state)
        cluster.sessions.append(node)
        cluster.total_tokens += node.tokens_used
        if state in ("working", "ready"):
            cluster.active_agent_count += 1

    clusters = list(project_clusters.values())
    if default_cluster.sessions:
        clusters.append(default_cluster)
    return clusters


@router.get("/projects", response_model=list[ProjectClusterModel])
async def list_session_map_projects(
    state_filter: AgentState | None = Query(None, description="Optional agent state filter"),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectClusterModel]:
    """Retrieves all projects with nested session topologies."""
    return await _load_clusters(db, state_filter)


@router.get("/cockpit", response_model=FleetCockpitSummary)
async def get_fleet_cockpit_summary(
    db: AsyncSession = Depends(get_db),
) -> FleetCockpitSummary:
    """Retrieves fleet overview metrics across projects and agents."""
    clusters = await _load_clusters(db)
    sessions = [session for cluster in clusters for session in cluster.sessions]
    states = Counter(session.state for session in sessions)

    return FleetCockpitSummary(
        total_projects=len(clusters),
        total_sessions=len(sessions),
        total_agents=len(sessions),
        working_agents=states["working"],
        ready_agents=states["ready"],
        waiting_input_agents=states["waiting_input"],
        error_agents=states["error"],
        total_tokens_consumed=sum(session.tokens_used for session in sessions),
        top_active_sessions=sorted(sessions, key=lambda s: s.last_active_at, reverse=True)[:10],
    )


@router.post("/search", response_model=SessionSearchResponse)
async def search_session_map(
    request: SessionSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionSearchResponse:
    """Full-text and metadata search across projects and session nodes."""
    clusters = await _load_clusters(db, request.state)
    q = request.query.strip().lower()

    hits: list[SessionSearchHit] = []

    for cluster in clusters:
        if request.project_id and cluster.id != request.project_id:
            continue

        for session in cluster.sessions:
            match_score = 0.0
            snippet = ""

            title_lower = session.title.lower()
            task_lower = (session.current_task or "").lower()
            tags_str = " ".join(session.tags).lower()
            agent_str = session.agent_name.lower()

            if q in title_lower:
                match_score += 1.0
                snippet = f"Title matched: {session.title}"
            elif q in task_lower:
                match_score += 0.8
                snippet = f"Active task: {session.current_task}"
            elif q in tags_str:
                match_score += 0.6
                snippet = f"Tag: #{q}"
            elif q in agent_str:
                match_score += 0.5
                snippet = f"Agent: {session.agent_name}"
            elif q in cluster.name.lower():
                match_score += 0.3
                snippet = f"Project: {cluster.name}"

            if match_score > 0.0:
                hits.append(
                    SessionSearchHit(
                        session=session,
                        project_name=cluster.name,
                        relevance_score=match_score,
                        matched_snippet=snippet,
                    )
                )

    hits.sort(key=lambda h: h.relevance_score, reverse=True)

    return SessionSearchResponse(
        query=request.query,
        total_hits=len(hits),
        hits=hits,
    )
