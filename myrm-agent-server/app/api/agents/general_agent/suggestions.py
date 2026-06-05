"""General Agent API — autonomous decision-making agent with streaming SSE."""

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic.alias_generators import to_camel

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.types import ModelConfig

logger = logging.getLogger(__name__)

router = APIRouter()

_SUGGESTIONS_PROMPT = (
    "Based on the conversation below, generate exactly 3 concise follow-up questions "
    "the user might want to ask next. Match the language of the conversation. "
    "Return ONLY a JSON array of strings, no explanation.\n\n"
    "Conversation:\n{conversation}\n\nJSON array:"
)


class SuggestionsRequest(BaseModel):
    chat_history: list[list[str]]

    class Config:
        alias_generator = to_camel
        populate_by_name = True


@router.post("/suggestions")
@limiter.limit(settings.rate_limit.chat)
async def get_suggestions(
    request: SuggestionsRequest,
    http_request: Request,
) -> JSONResponse:
    """Generate follow-up question suggestions using the filter model."""
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.utils.response_utils import success_response

    if not request.chat_history:
        return success_response(data={"suggestions": []})

    configs = await load_user_configs()
    providers_dict = configs.providers_dict
    if not providers_dict:
        return success_response(data={"suggestions": []})

    filter_cfg = _resolve_lite_model(providers_dict, configs.model_cfg)
    if filter_cfg is None:
        return success_response(data={"suggestions": []})

    try:
        from myrm_agent_harness.toolkits.llms import llm_manager

        llm = await llm_manager.get_llm_from_config(filter_cfg, streaming=False, api_keys=getattr(filter_cfg, "api_keys", None))

        conversation_text = "\n".join(f"{pair[0]}: {pair[1]}" for pair in request.chat_history[-6:] if len(pair) >= 2)
        prompt = _SUGGESTIONS_PROMPT.format(conversation=conversation_text)

        async with asyncio.timeout(15):
            result = await llm.ainvoke(prompt)

        content = result.content if hasattr(result, "content") else str(result)

        suggestions = _parse_suggestions(str(content))
        return success_response(data={"suggestions": suggestions})
    except TimeoutError:
        logger.warning("suggestions_generation_timed_out")
        return success_response(data={"suggestions": []})
    except Exception:
        logger.warning("suggestions_generation_failed", exc_info=True)
        return success_response(data={"suggestions": []})


def _resolve_lite_model(
    providers_dict: dict[str, object] | None,
    default_model_cfg: ModelConfig | None,
) -> ModelConfig | None:
    """Resolve filter model from providers config, fall back to default model."""
    from app.core.channel_bridge.config_parsers import extract_lite_model_config

    filter_cfg = extract_lite_model_config(providers_dict)
    if filter_cfg is not None:
        return filter_cfg
    return default_model_cfg


def _parse_suggestions(content: str) -> list[str]:
    """Extract a list of suggestion strings from LLM output.

    Tries JSON array first, falls back to line-based extraction.
    """
    content = content.strip()
    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end != -1:
        try:
            parsed = json.loads(content[start : end + 1])
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed[:5] if str(item).strip()]
        except (json.JSONDecodeError, ValueError):
            pass

    lines = [line.strip().lstrip("0123456789.-) ") for line in content.splitlines() if line.strip()]
    return [line for line in lines if len(line) > 5][:5]
