"""Gemini Live API support endpoints.

Provides ephemeral token generation and session configuration for the
frontend WebSocket-based Gemini Live voice mode.

Gemini Live connects the browser directly to Google's Multimodal Live API
via WebSocket, bypassing the server for audio streaming. The server's role:
  1. Securely generating ephemeral tokens (API key never exposed to browser)
  2. Resolving Agent profile for system instructions
  3. Building the WebSocket URL with proper authentication

[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs (POS: user config loader)
- app.services.agent.profile_resolver (POS: Agent profile resolver)

[OUTPUT]
- router: FastAPI APIRouter with Gemini Live voice endpoints

[POS]
Gemini Live API integration endpoints. Enables sub-300ms voice latency
by connecting browser directly to Google via WebSocket.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import verify_voice_enabled

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_voice_enabled)])

_GEMINI_LIVE_WS_BASE = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
_DEFAULT_GEMINI_LIVE_MODEL = "gemini-2.5-flash-preview-native-audio-dialog"


class GeminiLiveTokenRequest(BaseModel):
    agent_id: str | None = None
    model: str | None = None


class GeminiFunctionDeclaration(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class GeminiLiveTokenResponse(BaseModel):
    ws_url: str
    model: str
    instructions: str | None = None
    tools: list[GeminiFunctionDeclaration] = []


@router.post("/gemini-live-token", response_model=GeminiLiveTokenResponse)
async def create_gemini_live_token(req: GeminiLiveTokenRequest) -> GeminiLiveTokenResponse:
    """Generate a WebSocket URL with API key for Gemini Live connection.

    The frontend connects directly to Gemini's WebSocket endpoint.
    We use the API key approach (query param) which is simpler and sufficient
    for our architecture where the server is the trusted intermediary.
    """
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.services.agent.profile_resolver import get_agent_profile_resolver

    configs = await load_user_configs()
    providers = configs.providers_dict or {}

    google_key = _extract_google_api_key(providers)
    if not google_key:
        raise HTTPException(
            status_code=400,
            detail="Google API key not configured. Add it in Settings > Providers.",
        )

    resolver = get_agent_profile_resolver()
    agent_id = req.agent_id or "builtin-general"
    profile = await resolver.resolve(agent_id)

    model = req.model or _DEFAULT_GEMINI_LIVE_MODEL

    instructions: str | None = None
    if profile and profile.system_prompt:
        instructions = profile.system_prompt

    tools = _build_gemini_tools(profile.enabled_builtin_tools if profile else ())

    ws_url = f"{_GEMINI_LIVE_WS_BASE}?key={google_key}"

    return GeminiLiveTokenResponse(
        ws_url=ws_url,
        model=model,
        instructions=instructions,
        tools=tools,
    )


def _find_google_provider(providers: dict[str, object]) -> dict[str, object] | None:
    """Locate the Google/Gemini provider inside saved providers config."""
    provider_list = providers.get("providers")
    if not isinstance(provider_list, list):
        return None
    for provider in provider_list:
        if not isinstance(provider, dict):
            continue
        pid = str(provider.get("id", "")).lower()
        if "google" in pid or "gemini" in pid:
            return provider
    return None


def _extract_google_api_key(providers: dict[str, object]) -> str | None:
    """Return the active Google/Gemini API key."""
    provider = _find_google_provider(providers)
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


_GEMINI_TOOL_CATALOG: dict[str, GeminiFunctionDeclaration] = {
    "web_search": GeminiFunctionDeclaration(
        name="web_search",
        description="Search the web for current information. Use when the user asks about recent events, facts, or anything you're unsure about.",
        parameters={"type": "object", "properties": {"query": {"type": "string", "description": "Search query"}}, "required": ["query"]},
    ),
    "memory": GeminiFunctionDeclaration(
        name="memory_search_tool",
        description=(
            "Unified search across long-term memory, wiki vault, and prior conversations. "
            "Use corpus=memory for preferences/facts, sessions for chat history, wiki for docs."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "corpus": {
                    "type": "string",
                    "enum": ["memory", "wiki", "sessions", "all"],
                    "description": "Corpus to search (default memory)",
                },
            },
            "required": ["query"],
        },
    ),
    "file_ops": GeminiFunctionDeclaration(
        name="file_ops",
        description="Read, write, or list files in the workspace.",
        parameters={"type": "object", "properties": {"action": {"type": "string", "description": "File operation (read, write, or list)"}, "path": {"type": "string", "description": "File path"}}, "required": ["action", "path"]},
    ),
    "code_execute": GeminiFunctionDeclaration(
        name="code_execute",
        description="Execute code in a sandboxed environment and return the result.",
        parameters={"type": "object", "properties": {"code": {"type": "string", "description": "Code to execute"}, "language": {"type": "string", "description": "Programming language"}}, "required": ["code"]},
    ),
    "browser": GeminiFunctionDeclaration(
        name="browser",
        description="Browse a webpage and extract its content.",
        parameters={"type": "object", "properties": {"url": {"type": "string", "description": "URL to browse"}}, "required": ["url"]},
    ),
    "kanban": GeminiFunctionDeclaration(
        name="kanban",
        description="Manage tasks on the kanban board: create, update, or query tasks.",
        parameters={"type": "object", "properties": {"action": {"type": "string", "description": "Kanban action (create, update, or query)"}, "description": {"type": "string", "description": "Task description or query"}}, "required": ["action", "description"]},
    ),
}

_ALWAYS_AVAILABLE_TOOL = GeminiFunctionDeclaration(
    name="run_background_task",
    description="Delegate a complex task to run in the background. Use for long-running operations that shouldn't block the voice conversation.",
    parameters={"type": "object", "properties": {"task": {"type": "string", "description": "Detailed description of the task to run"}}, "required": ["task"]},
)


def _build_gemini_tools(enabled_builtin_tools: tuple[str, ...] | Sequence[str]) -> list[GeminiFunctionDeclaration]:
    """Build function declarations for Gemini Live from agent's enabled tools."""
    tools: list[GeminiFunctionDeclaration] = [_ALWAYS_AVAILABLE_TOOL]
    for tool_key in enabled_builtin_tools:
        if tool_key in _GEMINI_TOOL_CATALOG:
            tools.append(_GEMINI_TOOL_CATALOG[tool_key])
    return tools
