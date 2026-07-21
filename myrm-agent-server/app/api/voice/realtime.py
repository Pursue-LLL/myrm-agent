"""OpenAI Realtime API support endpoints.

Provides ephemeral token generation, tool execution proxy, and transcript
persistence for the frontend WebRTC-based Realtime voice mode.

The Realtime mode connects the browser directly to OpenAI's Realtime API
via WebRTC (RTCPeerConnection), bypassing the server for audio streaming.
The server's role is limited to:
  1. Securely generating ephemeral client tokens (API key never exposed)
  2. Executing tool calls proxied from the Realtime session
  3. Persisting conversation transcripts to chat history

[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs (POS: user config loader)
- app.services.agent.profile_resolver (POS: Agent profile resolver)
- app.api.voice.voice_memory_context::voice_memory_context_from (POS: voice memory ACL SSOT)
- app.api.voice.tool_catalog (POS: dynamic memory_search_tool voice declarations)

[OUTPUT]
- router: FastAPI APIRouter with Realtime voice endpoints

[POS]
OpenAI Realtime API integration endpoints. Enables sub-300ms voice latency
by connecting browser directly to OpenAI via WebRTC.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import verify_voice_enabled
from app.api.voice.voice_memory_context import VoiceMemoryContext, voice_memory_context_from

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_voice_enabled)])

_OPENAI_REALTIME_SESSIONS_URL = "https://api.openai.com/v1/realtime/sessions"
_DEFAULT_REALTIME_MODEL = "gpt-realtime-2"
_DEFAULT_REALTIME_VOICE = "verse"

REALTIME_VOICES = (
    "alloy",
    "ash",
    "ballad",
    "cedar",
    "coral",
    "echo",
    "marin",
    "sage",
    "shimmer",
    "verse",
)


class RealtimeTokenRequest(BaseModel):
    agent_id: str | None = None
    voice: str | None = None
    model: str | None = None


class RealtimeToolDef(BaseModel):
    type: str = "function"
    name: str
    description: str
    parameters: dict[str, Any]


class RealtimeTokenResponse(BaseModel):
    client_secret: str
    model: str
    voice: str
    expires_at: int | None = None
    instructions: str | None = None
    tools: list[RealtimeToolDef] = []


class RealtimeToolExecRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    agent_id: str | None = None
    chat_id: str | None = None


class RealtimeToolExecResponse(BaseModel):
    result: Any
    error: str | None = None


class RealtimeTranscriptRequest(BaseModel):
    chat_id: str
    entries: list[dict[str, str]]


@router.post("/realtime-token", response_model=RealtimeTokenResponse)
async def create_realtime_token(req: RealtimeTokenRequest) -> RealtimeTokenResponse:
    """Generate an ephemeral client secret for OpenAI Realtime WebRTC connection."""
    import httpx

    from app.core.channel_bridge.config_loader import load_user_configs
    from app.services.agent.profile_resolver import get_agent_profile_resolver

    configs = await load_user_configs()
    providers = configs.providers_dict or {}

    openai_key = _extract_openai_api_key(providers)
    if not openai_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API key not configured. Add it in Settings > Providers.",
        )

    resolver = get_agent_profile_resolver()
    agent_id = req.agent_id or "builtin-general"
    profile = await resolver.resolve(agent_id)

    model = req.model or _DEFAULT_REALTIME_MODEL
    if profile and profile.model and "realtime" in profile.model:
        model = profile.model

    voice = req.voice or _DEFAULT_REALTIME_VOICE
    voice_dict = configs.voice_dict or {}
    if not req.voice and voice_dict.get("ttsVoice"):
        configured_voice = str(voice_dict["ttsVoice"])
        if configured_voice in REALTIME_VOICES:
            voice = configured_voice

    instructions: str | None = None
    if profile and profile.system_prompt:
        instructions = profile.system_prompt

    memory_context = voice_memory_context_from(
        configs.personal_settings_dict or {},
        profile.enabled_builtin_tools if profile else (),
    )
    tools = _build_realtime_tools(
        profile.enabled_builtin_tools if profile else (),
        memory_context,
    )

    openai_base = _extract_openai_base_url(providers)
    sessions_url = f"{openai_base}/realtime/sessions" if openai_base else _OPENAI_REALTIME_SESSIONS_URL

    session_payload: dict[str, Any] = {
        "model": model,
        "voice": voice,
        "modalities": ["audio", "text"],
        "input_audio_transcription": {"model": "gpt-4o-mini-transcribe"},
        "turn_detection": {"type": "server_vad"},
    }
    if instructions:
        session_payload["instructions"] = instructions
    if tools:
        session_payload["tools"] = [
            {"type": t.type, "name": t.name, "description": t.description, "parameters": t.parameters}
            for t in tools
        ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            sessions_url,
            headers={
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json",
            },
            json=session_payload,
        )

    if resp.status_code != 200:
        logger.error("OpenAI Realtime session creation failed: %s %s", resp.status_code, resp.text[:200])
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI Realtime API error: {resp.status_code}",
        )

    data = resp.json()
    client_secret = data.get("client_secret", {})

    return RealtimeTokenResponse(
        client_secret=client_secret.get("value", "") if isinstance(client_secret, dict) else str(client_secret),
        model=model,
        voice=voice,
        expires_at=client_secret.get("expires_at") if isinstance(client_secret, dict) else None,
        instructions=instructions,
        tools=tools,
    )


@router.post("/realtime-tool-exec", response_model=RealtimeToolExecResponse)
async def execute_realtime_tool(req: RealtimeToolExecRequest) -> RealtimeToolExecResponse:
    """Execute a tool call proxied from the Realtime WebRTC session.

    When the Realtime API emits a function_call, the frontend proxies it here.
    Uses a lightweight Agent invocation (single-tool mode) to execute the tool
    within the Agent's security and permission context.
    """
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.services.agent.streaming import ai_agent_service_stream

    try:
        configs = await load_user_configs()
        providers = configs.providers_dict or {}

        from app.services.agent.profile_resolver import (
            DEFAULT_ENABLED_BUILTIN_TOOLS,
            get_agent_profile_resolver,
        )

        agent_id = req.agent_id or "builtin-general"
        resolver = get_agent_profile_resolver()
        profile = await resolver.resolve(agent_id)
        enabled_builtin_tools = (
            list(profile.enabled_builtin_tools) if profile else list(DEFAULT_ENABLED_BUILTIN_TOOLS)
        )
        memory_settings = configs.personal_settings_dict or {}
        memory_context = voice_memory_context_from(memory_settings, enabled_builtin_tools)

        lite_query = (
            f"Execute tool '{req.tool_name}' with arguments: "
            f"{_safe_json_str(req.arguments)}. "
            "Return only the tool result, no additional commentary."
        )

        from app.core.channel_bridge.config_parsers import (
            extract_lite_model_config,
            extract_retrieval_models,
        )

        lite_model = extract_lite_model_config(providers)
        embedding_cfg, reranker_cfg = extract_retrieval_models(configs.retrieval_dict)

        from app.ai_agents.agents import GeneralAgentParams

        _ensure_model_rebuild_for_tool_exec()

        params = GeneralAgentParams(
            query=lite_query,
            model_cfg=lite_model or configs.model_cfg,
            chat_id=req.chat_id or "realtime-tool",
            message_id=f"rt-tool-{req.tool_name}",
            agent_id=agent_id,
            channel_name="realtime_voice",
            providers_dict=providers,
            embedding_config=embedding_cfg,
            reranker_config=reranker_cfg,
            enable_memory=memory_context.enable_memory,
            enable_conversation_search=memory_context.enable_conversation_search,
            enable_wiki=memory_context.enable_wiki,
            fetch_raw_webpage=bool(memory_settings.get("fetchRawWebpage")),
            enable_memory_auto_extraction=bool(memory_settings.get("enableMemoryAutoExtraction", True)),
        )

        result_parts: list[str] = []
        async for event in ai_agent_service_stream(params):
            if event.get("type") == "message":
                chunk = str(event.get("data", ""))
                if chunk:
                    result_parts.append(chunk)

        return RealtimeToolExecResponse(result="".join(result_parts) or "Done")
    except Exception as exc:
        logger.warning("Realtime tool execution failed: %s(%s)", req.tool_name, exc)
        return RealtimeToolExecResponse(
            result=None,
            error=f"Tool execution failed: {exc}",
        )


@router.post("/realtime-transcript")
async def persist_realtime_transcript(req: RealtimeTranscriptRequest) -> dict[str, bool]:
    """Persist voice conversation transcript entries to chat history."""
    from datetime import datetime, timezone

    from app.services.chat import ChatService

    try:
        now = datetime.now(tz=timezone.utc)
        tz_name = "UTC"
        for entry in req.entries:
            role = entry.get("role", "user")
            text = entry.get("text", "")
            if not text.strip():
                continue
            await ChatService.append_message(
                chat_id=req.chat_id,
                role=role,
                content=text,
                sent_at=now,
                sent_timezone=tz_name,
                extra_data={"source": "realtime_voice"},
            )
        return {"ok": True}
    except Exception as exc:
        logger.warning("Transcript persistence failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _find_openai_provider(providers: dict[str, object]) -> dict[str, object] | None:
    """Locate the OpenAI provider inside a saved providers config (``{"providers": [...]}``).

    Providers persist as a list of ``ProviderConfig`` (see frontend ``providerTypes.ts``), each
    with ``id`` / ``apiUrl`` / ``apiKeys: [{key, isActive}]`` — not a dict keyed by id.
    """
    provider_list = providers.get("providers")
    if not isinstance(provider_list, list):
        return None
    for provider in provider_list:
        if isinstance(provider, dict) and "openai" in str(provider.get("id", "")).lower():
            return provider
    return None


def _extract_openai_api_key(providers: dict[str, object]) -> str | None:
    """Return the active OpenAI key (a relay virtual key under SaaS zero-secret mode)."""
    provider = _find_openai_provider(providers)
    if provider is None:
        return None
    api_keys = provider.get("apiKeys")
    if not isinstance(api_keys, list):
        return None
    fallback: str | None = None
    for entry in api_keys:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if not isinstance(key, str) or not key.strip():
            continue
        if entry.get("isActive"):
            return key.strip()
        fallback = fallback or key.strip()
    return fallback


def _extract_openai_base_url(providers: dict[str, object]) -> str | None:
    """Return the OpenAI base URL (the relay endpoint under SaaS zero-secret mode).

    The configured ``apiUrl`` already carries the API version segment (e.g. ``/v1``), so callers
    append only the resource path — never a second ``/v1`` — keeping direct and relay modes aligned.
    """
    provider = _find_openai_provider(providers)
    if provider is None:
        return None
    api_url = provider.get("apiUrl")
    if isinstance(api_url, str) and api_url.strip():
        return api_url.strip().rstrip("/")
    return None


def _safe_json_str(obj: object) -> str:
    """Serialize to JSON string safely."""
    import json

    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


_REALTIME_TOOL_CATALOG: dict[str, RealtimeToolDef] = {
    "web_search": RealtimeToolDef(
        name="web_search",
        description="Search the web for current information. Use when the user asks about recent events, facts, or anything you're unsure about.",
        parameters={"type": "object", "properties": {"query": {"type": "string", "description": "Search query"}}, "required": ["query"]},
    ),
    "file_ops": RealtimeToolDef(
        name="file_ops",
        description="Read, write, or list files in the workspace.",
        parameters={"type": "object", "properties": {"action": {"type": "string", "enum": ["read", "write", "list"], "description": "File operation"}, "path": {"type": "string", "description": "File path"}}, "required": ["action", "path"]},
    ),
    "code_execute": RealtimeToolDef(
        name="code_execute",
        description="Execute code (Python, shell, etc.) in a sandboxed environment and return the result.",
        parameters={"type": "object", "properties": {"code": {"type": "string", "description": "Code to execute"}, "language": {"type": "string", "description": "Programming language", "default": "python"}}, "required": ["code"]},
    ),
    "browser": RealtimeToolDef(
        name="browser",
        description="Browse a webpage and extract its content.",
        parameters={"type": "object", "properties": {"url": {"type": "string", "description": "URL to browse"}}, "required": ["url"]},
    ),
    "kanban": RealtimeToolDef(
        name="kanban",
        description="Manage tasks on the kanban board: create, update, or query tasks.",
        parameters={"type": "object", "properties": {"action": {"type": "string", "enum": ["create", "update", "query"], "description": "Kanban action"}, "description": {"type": "string", "description": "Task description or query"}}, "required": ["action", "description"]},
    ),
}

_ALWAYS_AVAILABLE_TOOL = RealtimeToolDef(
    name="run_background_task",
    description="Delegate a complex task to run in the background. Use for long-running operations that shouldn't block the voice conversation. The result will be available later.",
    parameters={"type": "object", "properties": {"task": {"type": "string", "description": "Detailed description of the task to run"}}, "required": ["task"]},
)


def _build_realtime_tools(
    enabled_builtin_tools: tuple[str, ...] | Sequence[str],
    memory_context: VoiceMemoryContext,
) -> list[RealtimeToolDef]:
    """Build tool definitions for OpenAI Realtime session from agent tools and memory ACL."""
    from app.api.voice.tool_catalog import (
        build_realtime_memory_tool,
        include_memory_search_in_voice_catalog,
    )

    tools: list[RealtimeToolDef] = [_ALWAYS_AVAILABLE_TOOL]
    for tool_key in enabled_builtin_tools:
        if tool_key == "memory":
            if include_memory_search_in_voice_catalog(memory_context, enabled_builtin_tools):
                tools.append(build_realtime_memory_tool(memory_context))
            continue
        if tool_key in _REALTIME_TOOL_CATALOG:
            tools.append(_REALTIME_TOOL_CATALOG[tool_key])
    return tools


_tool_exec_model_rebuilt = False


def _ensure_model_rebuild_for_tool_exec() -> None:
    """One-time Pydantic model rebuild for tool-exec endpoint."""
    global _tool_exec_model_rebuilt  # noqa: PLW0603
    if _tool_exec_model_rebuilt:
        return
    from myrm_agent_harness.toolkits.retriever.embedding.factory import (
        EmbeddingConfig,
    )
    from myrm_agent_harness.toolkits.retriever.reranker.factory import (
        RerankerConfig,
    )

    from app.ai_agents.agents import GeneralAgentParams

    GeneralAgentParams.model_rebuild(
        _types_namespace={
            "EmbeddingConfig": EmbeddingConfig,
            "RerankerConfig": RerankerConfig,
        }
    )
    _tool_exec_model_rebuilt = True
