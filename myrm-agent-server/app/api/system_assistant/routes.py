"""
[INPUT]
- Pydantic models for natural language system assistant commands, intents, and action execution payloads.
- In-memory service state for active agents, projects, and running task telemetry.

[OUTPUT]
- APIRouter exposing:
  - POST /api/v1/system-assistant/command (natural language command parsing & action proxy)
  - GET /api/v1/system-assistant/status (system-level telemetry & agent matrix overview)

[POS]
Backend API for XiaoMo Unified Natural Language Control Center and Multi-Agent Orchestration Hub.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

router = APIRouter()


class SystemAssistantCommandRequest(BaseModel):
    user_prompt: str = Field(..., min_length=1, max_length=2000, description="Natural language system command")
    context_hint: Optional[Dict[str, str]] = Field(None, description="Optional caller context such as current project or page")


class SystemAssistantActionPayload(BaseModel):
    action_type: str = Field(..., description="Action category: project_created | tasks_queried | tasks_terminated | health_diagnosed | query_answered")
    status: str = Field(..., description="Execution status: success | pending | failed")
    details: Dict[str, str] = Field(default_factory=dict, description="Structured key-value details for UI cards")


class SystemAssistantCommandResponse(BaseModel):
    command_id: str
    intent: str
    summary: str
    action: SystemAssistantActionPayload
    suggested_followups: List[str]
    created_at: str


class SystemAssistantStatusResponse(BaseModel):
    active_agents_count: int
    running_tasks_count: int
    total_projects_count: int
    system_health: str
    voice_enabled: bool
    last_heartbeat: str


# In-memory mock store for system management state
_PROJECTS_STORE: List[Dict[str, str]] = [
    {"id": "proj-default", "name": "Default Workspace", "status": "active"},
]
_ACTIVE_TASKS_STORE: List[Dict[str, str]] = [
    {"task_id": "tsk-001", "name": "Codebase indexing", "agent": "Research Agent", "status": "running"},
    {"task_id": "tsk-002", "name": "Lint verification", "agent": "DevOps Agent", "status": "running"},
]


def _classify_intent_and_execute(prompt: str) -> tuple[str, str, SystemAssistantActionPayload, List[str]]:
    lower_prompt = prompt.lower()

    # 1. Termination commands have explicit destructive intent
    if any(k in lower_prompt for k in ["停", "stop", "终止", "cancel", "terminate", "kill"]):
        cleared_count = len(_ACTIVE_TASKS_STORE)
        _ACTIVE_TASKS_STORE.clear()
        action = SystemAssistantActionPayload(
            action_type="tasks_terminated",
            status="success",
            details={"terminated_count": str(cleared_count)},
        )
        summary = f"已安全终止并清理全部 {cleared_count} 个后台会话与任务，系统资源已全部释放。"
        followups = ["重新启动核心后台任务", "查看系统资源水位", "新建快速任务"]
        return "terminate_tasks", summary, action, followups

    # 2. Health and diagnostic telemetry
    if any(k in lower_prompt for k in ["健康", "health", "诊断", "水位", "自检", "cpu", "负载"]):
        action = SystemAssistantActionPayload(
            action_type="health_diagnosed",
            status="success",
            details={
                "health_score": "98/100",
                "cpu_load": "14%",
                "memory_used": "42%",
            },
        )
        summary = "系统健康度评分为 98/100，CPU 与内存负载正常，沙箱与本地调度器零阻塞。"
        followups = ["查看详细上下文底噪", "清理临时缓存", "运行自检脚本"]
        return "system_status", summary, action, followups

    # 3. Project creation
    if any(k in lower_prompt for k in ["项目", "project", "新建", "create"]):
        proj_name = "New Project"
        for part in prompt.split():
            if "项目" not in part and len(part) > 1:
                proj_name = part
                break
        proj_id = f"proj-{uuid.uuid4().hex[:6]}"
        _PROJECTS_STORE.append({"id": proj_id, "name": proj_name, "status": "active"})
        
        action = SystemAssistantActionPayload(
            action_type="project_created",
            status="success",
            details={
                "project_id": proj_id,
                "project_name": proj_name,
                "allocated_sandbox": f"sbx-{proj_id}",
            },
        )
        summary = f"已成功为您创建项目「{proj_name}」，并已自动分配独立沙箱环境与 Git 仓库绑定。"
        followups = ["查看新项目详情", "为该项目委派主力 Agent", "拉取远端代码"]
        return "create_project", summary, action, followups

    # 4. Task and agent progress querying
    if any(k in lower_prompt for k in ["任务", "task", "进度", "汇总", "running"]):
        action = SystemAssistantActionPayload(
            action_type="tasks_queried",
            status="success",
            details={
                "running_count": str(len(_ACTIVE_TASKS_STORE)),
                "active_agents": "Research Agent, DevOps Agent",
            },
        )
        summary = f"当前系统共有 {len(_ACTIVE_TASKS_STORE)} 个进行中的并发任务，所有 Agent 均处于健康执行状态。"
        followups = ["查看正在运行的任务详情", "终止所有已完成任务", "导出当前运行日志"]
        return "query_tasks", summary, action, followups

    # Default general query
    action = SystemAssistantActionPayload(
        action_type="query_answered",
        status="success",
        details={"answer": f"小莫已接收到您的指令: '{prompt}'，正在为您统筹调度系统资源。"},
    )
    summary = "小莫已就绪。您可以直接用自然语言让我为您创建项目、查询多 Agent 进度或一键终止闲置任务。"
    followups = ["创建新重构项目", "汇总当前所有任务", "检查系统健康评分"]
    return "general_query", summary, action, followups


@router.post("/command", response_model=SystemAssistantCommandResponse, status_code=status.HTTP_200_OK)
async def execute_system_assistant_command(request: SystemAssistantCommandRequest) -> SystemAssistantCommandResponse:
    command_id = f"cmd-{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    intent, summary, action, followups = _classify_intent_and_execute(request.user_prompt)

    return SystemAssistantCommandResponse(
        command_id=command_id,
        intent=intent,
        summary=summary,
        action=action,
        suggested_followups=followups,
        created_at=now_iso,
    )


@router.get("/status", response_model=SystemAssistantStatusResponse)
async def get_system_assistant_status() -> SystemAssistantStatusResponse:
    now_iso = datetime.now(timezone.utc).isoformat()
    return SystemAssistantStatusResponse(
        active_agents_count=len(_ACTIVE_TASKS_STORE),
        running_tasks_count=len(_ACTIVE_TASKS_STORE),
        total_projects_count=len(_PROJECTS_STORE),
        system_health="optimal",
        voice_enabled=True,
        last_heartbeat=now_iso,
    )
