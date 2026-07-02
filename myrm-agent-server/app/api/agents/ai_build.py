"""AI-driven agent configuration generator.

Accepts a user intent and streams a complete AgentCreate-compatible JSON
payload, including recommended skill IDs, MCP IDs, and builtin tools.

[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs (POS: load merged user config bundles)
- app.core.channel_bridge.model_resolver::resolve_model_config, enrich_model_context_window
  (POS: business-layer model resolution)
- myrm_agent_harness.toolkits.llms.llm_manager::get_llm_from_config (POS: LangChain LLM construction)
- app.core.skills.store.service::skills_service (POS: Skill store singleton)
- app.schemas.streaming::SSEEnvelope (POS: 业务层 SSE 序列化防腐层)

[OUTPUT]
- POST /user-agents/ai-build: SSE stream of a structured JSON agent configuration

[POS]
AI Builder API: resolves the user's default model, queries installed skills/MCP,
then streams a complete agent config draft for the frontend to populate the edit form.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage
from myrm_agent_harness.api import ConfigIncompleteError
from myrm_agent_harness.toolkits.llms import llm_manager
from pydantic import BaseModel

from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_parsers import extract_mcp_configs
from app.core.channel_bridge.model_resolver import (
    enrich_model_context_window,
    resolve_model_config,
)
from app.core.skills.store.service import skills_service
from app.schemas.streaming import SSE_RESPONSE_HEADERS, SSEEnvelope
from app.services.agent.builtin_tool_ids import BUILTIN_TOOL_CATALOG

logger = logging.getLogger(__name__)

router = APIRouter()


class AIBuildRequest(BaseModel):
    intent: str
    locale: str | None = None


async def _collect_available_resources() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Query installed skills and configured MCP servers, returning compact summaries."""
    skill_summaries: list[dict[str, str]] = []
    try:
        all_skills = await skills_service.list_skills()
        for s in all_skills:
            if s.enabled:
                skill_summaries.append({"id": s.id, "name": s.name, "desc": s.description or ""})
    except Exception as exc:
        logger.warning("ai_build: failed to list skills: %s", exc)

    mcp_summaries: list[dict[str, str]] = []
    try:
        configs = await load_user_configs()
        if configs.mcp_dict:
            mcp_configs = extract_mcp_configs(configs.mcp_dict)
            for m in mcp_configs:
                mcp_summaries.append({"id": m.name, "name": m.name})
    except Exception as exc:
        logger.warning("ai_build: failed to list MCP servers: %s", exc)

    return skill_summaries, mcp_summaries


def _build_system_prompt(
    locale: str | None,
    skill_catalog: list[dict[str, str]],
    mcp_catalog: list[dict[str, str]],
    tool_catalog: list[dict[str, str]],
) -> str:
    skills_block = json.dumps(skill_catalog, ensure_ascii=False) if skill_catalog else "[]"
    mcp_block = json.dumps(mcp_catalog, ensure_ascii=False) if mcp_catalog else "[]"
    tools_block = json.dumps(tool_catalog, ensure_ascii=False)

    return f"""You are an expert AI Agent Configuration Generator.

Given a user's intent, generate a COMPLETE agent configuration as a single JSON object.

The JSON MUST have exactly these fields:
- "name": string, concise agent name (2-6 words)
- "description": string, one-sentence description of what this agent does
- "system_prompt": string, a well-structured Markdown system prompt with <role>, <rules>, <tone> sections
- "skill_ids": list of skill IDs from the AVAILABLE SKILLS below that are relevant to this agent
- "mcp_ids": list of MCP server IDs from the AVAILABLE MCP SERVERS below that are relevant
- "builtin_tools": list of builtin tool IDs from the AVAILABLE TOOLS below that are relevant

AVAILABLE SKILLS (only pick from these):
{skills_block}

AVAILABLE MCP SERVERS (only pick from these):
{mcp_block}

AVAILABLE BUILTIN TOOLS (only pick from these):
{tools_block}

CRITICAL RULES:
- Output ONLY valid JSON. No markdown fences, no explanations, no conversational filler.
- Only recommend skills/MCP/tools that actually match the user's intent. Don't include irrelevant ones.
- If no skills/MCP match, use empty lists.
- The system_prompt should be professional and well-structured.
- Output language: {locale or "auto-detect based on user intent"}.
- The name and description should match the locale language."""


async def _ai_build_stream(intent: str, locale: str | None) -> AsyncGenerator[str, None]:
    try:
        configs = await load_user_configs()
        providers_dict = configs.providers_dict if configs else None
        model_cfg = resolve_model_config(providers_dict)
        model_cfg = enrich_model_context_window(model_cfg, providers_dict)
        model_cfg = model_cfg.model_copy(update={"temperature": 0.5, "streaming": True})

        api_keys = model_cfg.api_keys
        llm = await llm_manager.get_llm_from_config(model_cfg, api_keys=api_keys)

        skill_catalog, mcp_catalog = await _collect_available_resources()
        system_prompt = _build_system_prompt(
            locale,
            skill_catalog,
            mcp_catalog,
            list(BUILTIN_TOOL_CATALOG),
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Create an agent for: {intent}"),
        ]

        async for chunk in llm.astream(messages):
            if chunk.content:
                envelope = SSEEnvelope(type="content", data=str(chunk.content))
                yield envelope.to_sse_chunk()

        envelope = SSEEnvelope(type="done", data=True)
        yield envelope.to_sse_chunk()

    except Exception as exc:
        logger.error("AI Build failed: %s", exc)
        envelope = SSEEnvelope(type="error", error=f"AI Build failed: {exc!s}")
        yield envelope.to_sse_chunk()


@router.post("/ai-build")
async def ai_build(request: AIBuildRequest) -> StreamingResponse:
    """Generate a complete agent configuration from a natural-language intent."""
    if not request.intent or not request.intent.strip():
        raise HTTPException(status_code=400, detail="Intent cannot be empty")

    try:
        configs = await load_user_configs()
        providers_dict = configs.providers_dict if configs else None
        resolve_model_config(providers_dict)
    except ConfigIncompleteError as exc:
        logger.warning("AI Build blocked: %s", exc.technical_details)
        raise HTTPException(
            status_code=422,
            detail="LLM provider is not configured. Please add a model provider in Settings before using this feature.",
        ) from exc

    return StreamingResponse(
        _ai_build_stream(request.intent, request.locale),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )
