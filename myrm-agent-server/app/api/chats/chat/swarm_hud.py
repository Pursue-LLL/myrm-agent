"""[INPUT]
- Path parameters: chat_id, rule_id, risk_id
- Request bodies: ConfigureSwarmRequest, AssignSubagentTasksRequest, RecordRecalledRulesRequest, ToggleRuleActiveRequest, RegisterOwnerRisksRequest, ConfirmRiskRequest
- SwarmExecutionService: Domain service

[OUTPUT]
- Swarm coordination endpoints: config, task boundaries, recalled rules HUD, owner risk checklist

[POS]
API route layer for Swarm Coordination, Memory Recall HUD & Owner Risk Checklist (Item 42 P0).
Strictly under 240 lines. Zero `Any`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.response_utils import error_response, success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.swarm import SwarmExecutionService
from myrm_agent_harness.toolkits.swarm import (
    OwnerRiskItem,
    RecalledRuleItem,
    RiskSeverityLevel,
    SwarmSubagentTask,
)

router = APIRouter()


class ConfigureSwarmRequest(BaseModel):
    enabled: bool = Field(..., description="Whether Swarm multi-agent coordination is enabled")
    concurrency_quota: int = Field(default=5, ge=1, le=10, description="Parallel subagent allocation quota")


class SubagentTaskInput(BaseModel):
    task_id: str = Field(..., min_length=1)
    role_title: str = Field(..., min_length=1)
    boundary_description: str = Field(..., min_length=1)
    status: Literal["pending", "running", "completed", "failed"] = Field(default="pending")
    current_step: str = Field(default="")
    assigned_tools: list[str] = Field(default_factory=list)


class AssignSubagentTasksRequest(BaseModel):
    tasks: list[SubagentTaskInput] = Field(..., min_length=1)


class RecalledRuleInput(BaseModel):
    rule_id: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    source_turn_id: str = Field(default="")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_active: bool = Field(default=True)
    category: str = Field(default="business_rule")


class RecordRecalledRulesRequest(BaseModel):
    rules: list[RecalledRuleInput] = Field(..., min_length=1)


class ToggleRuleActiveRequest(BaseModel):
    is_active: bool = Field(...)


class OwnerRiskInput(BaseModel):
    risk_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    severity: RiskSeverityLevel = Field(default="medium")
    external_constraint_type: str = Field(default="compliance")
    remediation_hint: str = Field(default="")


class RegisterOwnerRisksRequest(BaseModel):
    risks: list[OwnerRiskInput] = Field(..., min_length=1)


class ConfirmRiskRequest(BaseModel):
    is_confirmed: bool = Field(...)
    confirmed_by: str = Field(default="")


@router.post("/{chat_id}/swarm/config", response_model=StandardSuccessResponse)
async def set_swarm_config(
    body: ConfigureSwarmRequest,
    chat_id: str = Path(..., description="Chat session identifier"),
) -> JSONResponse:
    svc = SwarmExecutionService.get_instance()
    cfg = svc.set_swarm_config(chat_id, enabled=body.enabled, concurrency_quota=body.concurrency_quota)
    return success_response(data={
        "enabled": cfg.enabled,
        "concurrency_quota": cfg.concurrency_quota,
        "auto_decompose": cfg.auto_decompose,
        "session_id": cfg.session_id,
    })


@router.get("/{chat_id}/swarm/config", response_model=StandardSuccessResponse)
async def get_swarm_config(
    chat_id: str = Path(..., description="Chat session identifier"),
) -> JSONResponse:
    svc = SwarmExecutionService.get_instance()
    cfg = svc.get_swarm_config(chat_id)
    return success_response(data={
        "enabled": cfg.enabled,
        "concurrency_quota": cfg.concurrency_quota,
        "auto_decompose": cfg.auto_decompose,
        "session_id": cfg.session_id,
    })


@router.post("/{chat_id}/swarm/tasks", response_model=StandardSuccessResponse)
async def assign_subagent_tasks(
    body: AssignSubagentTasksRequest,
    chat_id: str = Path(..., description="Chat session identifier"),
) -> JSONResponse:
    svc = SwarmExecutionService.get_instance()
    tasks = [
        SwarmSubagentTask(
            task_id=t.task_id,
            role_title=t.role_title,
            boundary_description=t.boundary_description,
            status=t.status,
            current_step=t.current_step,
            assigned_tools=t.assigned_tools,
        )
        for t in body.tasks
    ]
    assigned = svc.assign_subagent_tasks(chat_id, tasks)
    return success_response(data=[
        {
            "task_id": item.task_id,
            "role_title": item.role_title,
            "boundary_description": item.boundary_description,
            "status": item.status,
            "current_step": item.current_step,
            "assigned_tools": item.assigned_tools,
        }
        for item in assigned
    ])


@router.get("/{chat_id}/swarm/tasks", response_model=StandardSuccessResponse)
async def get_subagent_tasks(
    chat_id: str = Path(..., description="Chat session identifier"),
) -> JSONResponse:
    svc = SwarmExecutionService.get_instance()
    tasks = svc.get_subagent_tasks(chat_id)
    return success_response(data=[
        {
            "task_id": item.task_id,
            "role_title": item.role_title,
            "boundary_description": item.boundary_description,
            "status": item.status,
            "current_step": item.current_step,
            "assigned_tools": item.assigned_tools,
        }
        for item in tasks
    ])


@router.post("/{chat_id}/swarm/recalled-rules", response_model=StandardSuccessResponse)
async def record_recalled_rules(
    body: RecordRecalledRulesRequest,
    chat_id: str = Path(..., description="Chat session identifier"),
) -> JSONResponse:
    svc = SwarmExecutionService.get_instance()
    rules = [
        RecalledRuleItem(
            rule_id=r.rule_id,
            summary=r.summary,
            source_turn_id=r.source_turn_id,
            confidence=r.confidence,
            is_active=r.is_active,
            category=r.category,
        )
        for r in body.rules
    ]
    recorded = svc.record_recalled_rules(chat_id, rules)
    return success_response(data=[
        {
            "rule_id": item.rule_id,
            "summary": item.summary,
            "source_turn_id": item.source_turn_id,
            "confidence": item.confidence,
            "is_active": item.is_active,
            "category": item.category,
        }
        for item in recorded
    ])


@router.get("/{chat_id}/swarm/recalled-rules", response_model=StandardSuccessResponse)
async def get_recalled_rules(
    chat_id: str = Path(..., description="Chat session identifier"),
) -> JSONResponse:
    svc = SwarmExecutionService.get_instance()
    rules, prompt = svc.get_recalled_rules(chat_id)
    return success_response(data={
        "rules": [
            {
                "rule_id": item.rule_id,
                "summary": item.summary,
                "source_turn_id": item.source_turn_id,
                "confidence": item.confidence,
                "is_active": item.is_active,
                "category": item.category,
            }
            for item in rules
        ],
        "active_prompt": prompt,
    })


@router.patch("/{chat_id}/swarm/recalled-rules/{rule_id}", response_model=StandardSuccessResponse)
async def toggle_rule_active(
    body: ToggleRuleActiveRequest,
    chat_id: str = Path(..., description="Chat session identifier"),
    rule_id: str = Path(..., description="Rule identifier"),
) -> JSONResponse:
    svc = SwarmExecutionService.get_instance()
    updated = svc.toggle_rule_active(chat_id, rule_id, body.is_active)
    if updated is None:
        return error_response(code=404, message=f"Recalled rule {rule_id} not found")
    return success_response(data={
        "rule_id": updated.rule_id,
        "is_active": updated.is_active,
        "summary": updated.summary,
    })


@router.post("/{chat_id}/swarm/risks", response_model=StandardSuccessResponse)
async def register_owner_risks(
    body: RegisterOwnerRisksRequest,
    chat_id: str = Path(..., description="Chat session identifier"),
) -> JSONResponse:
    svc = SwarmExecutionService.get_instance()
    risks = [
        OwnerRiskItem(
            risk_id=item.risk_id,
            title=item.title,
            description=item.description,
            severity=item.severity,
            external_constraint_type=item.external_constraint_type,
            remediation_hint=item.remediation_hint,
        )
        for item in body.risks
    ]
    registered = svc.register_owner_risks(chat_id, risks)
    return success_response(data=[
        {
            "risk_id": item.risk_id,
            "title": item.title,
            "description": item.description,
            "severity": item.severity,
            "is_confirmed": item.is_confirmed,
            "confirmed_by": item.confirmed_by,
            "external_constraint_type": item.external_constraint_type,
            "remediation_hint": item.remediation_hint,
        }
        for item in registered
    ])


@router.get("/{chat_id}/swarm/risks", response_model=StandardSuccessResponse)
async def get_owner_risks(
    chat_id: str = Path(..., description="Chat session identifier"),
) -> JSONResponse:
    svc = SwarmExecutionService.get_instance()
    risks = svc.get_owner_risks(chat_id)
    return success_response(data=[
        {
            "risk_id": item.risk_id,
            "title": item.title,
            "description": item.description,
            "severity": item.severity,
            "is_confirmed": item.is_confirmed,
            "confirmed_by": item.confirmed_by,
            "external_constraint_type": item.external_constraint_type,
            "remediation_hint": item.remediation_hint,
        }
        for item in risks
    ])


@router.patch("/{chat_id}/swarm/risks/{risk_id}", response_model=StandardSuccessResponse)
async def confirm_owner_risk(
    body: ConfirmRiskRequest,
    chat_id: str = Path(..., description="Chat session identifier"),
    risk_id: str = Path(..., description="Risk identifier"),
) -> JSONResponse:
    svc = SwarmExecutionService.get_instance()
    updated = svc.set_risk_confirmation(chat_id, risk_id, body.is_confirmed, body.confirmed_by)
    if updated is None:
        return error_response(code=404, message=f"Risk item {risk_id} not found")
    return success_response(data={
        "risk_id": updated.risk_id,
        "is_confirmed": updated.is_confirmed,
        "confirmed_by": updated.confirmed_by,
        "title": updated.title,
    })
