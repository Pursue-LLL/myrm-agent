"""Follow-up question suggestions API.

[INPUT]
- core.channel_bridge.config_loader::load_user_configs (POS: load merged user config bundles)
- core.channel_bridge.config_parsers::extract_lite_model_config (POS: resolve lite/filter model)
- myrm_agent_harness.toolkits.llms.llm_manager::get_llm_from_config (POS: LangChain LLM construction)
- core.utils.chat_utils::extract_answer_text (POS: LLM 响应文本提取)
- utils.json_parsing::parse_llm_json_list (POS: 容错 JSON 数组解析 SSOT)

[OUTPUT]
- POST /agents/suggestions: JSON array of 3 concise follow-up questions

[POS]
Generates follow-up question suggestions from recent chat history using the
configured lite/filter model. Falls back to default model if no lite model set.
"""

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic.alias_generators import to_camel

from myrm_agent_harness.utils.json_parsing import parse_llm_json_list

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.types import ModelConfig
from app.core.utils.chat_utils import extract_answer_text

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Suggestions endpoint
# ---------------------------------------------------------------------------

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

        # 兼容 Anthropic 块列表 / reasoning 模型 content 空回退
        content = extract_answer_text(result)

        suggestions = _parse_suggestions(content)
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

    Prefers a JSON array parsed by :func:`parse_llm_json_list`, which
    tolerates fences, prose framing, unescaped newlines inside string
    literals, and format examples preceding the real array. Falls back to
    line-based extraction for non-JSON replies.
    """
    parsed = parse_llm_json_list(content)
    if parsed is not None:
        suggestions = [str(item).strip() for item in parsed[:5] if str(item).strip()]
        if suggestions:
            return suggestions

    lines = [line.strip().lstrip("0123456789.-) ") for line in content.splitlines() if line.strip()]
    return [line for line in lines if len(line) > 5][:5]
