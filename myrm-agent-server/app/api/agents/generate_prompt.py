"""Streaming system-prompt generation for saved agents.

[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs (POS: load merged user config bundles)
- app.core.channel_bridge.model_resolver::resolve_model_config, enrich_model_context_window
  (POS: business-layer model resolution)
- myrm_agent_harness.toolkits.llms.llm_manager::get_llm_from_config (POS: LangChain LLM construction)
- app.schemas.streaming::SSEEnvelope (POS: 业务层 SSE 序列化防腐层)

[OUTPUT]
- POST /user-agents/generate-prompt: SSE text stream of generated Markdown system prompt

[POS]
Thin API for the agent editor: resolves the user's default model and streams a draft system prompt.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage
from myrm_agent_harness.agent.config import ConfigIncompleteError
from myrm_agent_harness.toolkits.llms import llm_manager
from pydantic import BaseModel

from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.model_resolver import (
    enrich_model_context_window,
    resolve_model_config,
)
from app.schemas.streaming import SSE_RESPONSE_HEADERS, SSEEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


class PromptGenerateRequest(BaseModel):
    intent: str
    locale: str | None = None
    current_prompt: str | None = None


async def generate_prompt_stream(intent: str, locale: str | None, current_prompt: str | None) -> AsyncGenerator[str, None]:
    try:
        configs = await load_user_configs()
        providers_dict = configs.providers_dict if configs else None
        model_cfg = resolve_model_config(providers_dict)
        model_cfg = enrich_model_context_window(model_cfg, providers_dict)
        model_cfg = model_cfg.model_copy(update={"temperature": 0.7, "streaming": True})

        api_keys = model_cfg.api_keys
        llm = await llm_manager.get_llm_from_config(model_cfg, api_keys=api_keys)

        system_prompt = f"""You are an expert AI Prompt Engineer. Your task is to write a highly effective, structured System Prompt for an AI agent based on the user's intent.
The prompt MUST be written in Markdown format and include the following sections:
1. <role>: A clear definition of the agent's persona and expertise.
2. <rules>: A bulleted list of strict rules the agent must follow.
3. <tone>: The communication style and tone.
4. <examples> (optional): One or two brief examples of how the agent should respond.

CRITICAL INSTRUCTIONS:
- Do NOT include any conversational filler (like "Here is your prompt:"). Output ONLY the raw Markdown prompt text.
- You MUST output the prompt in the language corresponding to this locale: {locale or "auto-detect based on intent"}.
"""

        if current_prompt and current_prompt.strip():
            system_prompt += f"\n\nThe user already has an existing prompt. You should EDIT or ENHANCE it based on their new intent, rather than rewriting from scratch if the intent is just a minor addition.\n\nEXISTING PROMPT:\n{current_prompt}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"User Intent: {intent}"),
        ]

        async for chunk in llm.astream(messages):
            if chunk.content:
                envelope = SSEEnvelope(type="content", data=str(chunk.content))
                yield envelope.to_sse_chunk()

    except Exception as exc:
        logger.error("Failed to generate prompt: %s", exc)
        envelope = SSEEnvelope(type="error", error=f"Error generating prompt: {exc!s}")
        yield envelope.to_sse_chunk()


@router.post("/generate-prompt")
async def generate_prompt(request: PromptGenerateRequest) -> StreamingResponse:
    """Generate a structured system prompt based on user intent."""
    if not request.intent or not request.intent.strip():
        raise HTTPException(status_code=400, detail="Intent cannot be empty")

    try:
        # We call resolve_model_config here just to check if a model is configured
        # so we can return a 422 before starting the stream.
        configs = await load_user_configs()
        providers_dict = configs.providers_dict if configs else None
        resolve_model_config(providers_dict)
    except ConfigIncompleteError as exc:
        logger.warning("Prompt generation blocked: %s", exc.technical_details)
        raise HTTPException(
            status_code=422,
            detail="LLM provider is not configured. Please add a model provider in Settings before using this feature.",
        ) from exc

    return StreamingResponse(
        generate_prompt_stream(request.intent, request.locale, request.current_prompt),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )
