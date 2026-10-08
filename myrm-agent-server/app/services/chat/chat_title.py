"""Chat title generation orchestration.

[INPUT]
- core.utils.chat_utils::extract_answer_text (POS: LLM response content extraction)
- database.dto::_TitleModelConfig (POS: Title generation model configuration)

[OUTPUT]
- generate_chat_title: Generates concise chat title with resilience fallback

[POS]
Chat title generation layer decoupled from turn management.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, cast

from app.core.utils.chat_utils import extract_answer_text

if TYPE_CHECKING:
    from app.database.dto import _TitleModelConfig

logger = logging.getLogger(__name__)


def generate_fallback_title(content: str) -> str:
    """Generate deterministic fallback title from content snippet."""
    clean_title = re.sub(r"^(User|Assistant):\s*", "", content, flags=re.MULTILINE).strip()
    title = clean_title[:20]
    if len(title) < 3:
        return "Untitled Chat"
    return title + ("..." if len(clean_title) > 20 else "")


async def call_llm_for_title(content: str, title_model: "_TitleModelConfig") -> str:
    """Call LLM to summarize conversation into a concise title."""
    from langchain_core.messages import HumanMessage
    from myrm_agent_harness.toolkits.llms import llm_manager

    from app.core.types import ModelConfig
    from app.core.wire.enrich import enrich_model_config

    model_kwargs = dict(title_model.model_kwargs or {})
    model_kwargs.setdefault("temperature", 0.3)
    model_kwargs.setdefault("max_tokens", 1024)
    # A title never needs the output floor a thinking model would otherwise get.
    model_kwargs["supports_reasoning"] = False
    cfg = enrich_model_config(
        ModelConfig(
            model=title_model.model,
            api_key=title_model.api_key,
            base_url=title_model.base_url,
            model_kwargs=model_kwargs,
        )
    )
    llm = await llm_manager.get_llm_from_config(cfg, streaming=False)
    prompt = (
        "Summarize this conversation into a short title (5-15 characters). "
        "Reply strictly in the SAME LANGUAGE as the user input. Output ONLY the title:\n"
        f"<user_input>\n{content[:200]}\n</user_input>"
    )
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    title = extract_answer_text(response).strip().strip("\"'「」【】：:。.")
    title = re.sub(r"^(Title|标题|Chat Title)[:：\s]*", "", title, flags=re.IGNORECASE)
    if len(title) < 2 or len(title) > 50:
        return generate_fallback_title(content)
    return title


async def generate_chat_title(
    messages: list,
    title_model: "_TitleModelConfig | None" = None,
    fallback_title_model: "_TitleModelConfig | None" = None,
) -> str:
    """Generate concise title using lightweight model with multi-tier fallback."""
    from myrm_agent_harness.core.security.detection.leak_detector import redact_leaks
    from myrm_agent_harness.toolkits.llms.errors.resilient import resilient_llm_call

    dialogue_parts: list[str] = []
    user_count = 0
    for msg in messages:
        if getattr(msg, "role", "") == "user":
            dialogue_parts.append(f"User: {getattr(msg, 'content', '')}")
            user_count += 1
            if user_count >= 2:
                break
        elif getattr(msg, "role", "") == "assistant" and user_count > 0:
            dialogue_parts.append(f"Assistant: {getattr(msg, 'content', '')}")

    if not dialogue_parts:
        return "Untitled Chat"

    raw_content = "\n\n".join(dialogue_parts)[:2000]

    lang_match = re.search(r"```([a-zA-Z0-9_+-]+)", raw_content)
    lang = lang_match.group(1).strip() if lang_match else ""

    clean_content = re.sub(r"```.*?```", "", raw_content, flags=re.DOTALL)
    clean_content = re.sub(r"```.*$", "", clean_content, flags=re.DOTALL)
    clean_content = re.sub(r"<think>.*?</think>", "", clean_content, flags=re.DOTALL)
    clean_content = re.sub(r"<think>.*$", "", clean_content, flags=re.DOTALL)
    clean_content = re.sub(r"http[s]?://\S+", "", clean_content)
    clean_content = re.sub(r"<[^>]+>", "", clean_content)
    clean_content = re.sub(r"<[^>]*$", "", clean_content)
    clean_content = clean_content.strip()

    clean_content = redact_leaks(clean_content)

    has_code_block = "```" in raw_content
    stripped_for_check = re.sub(r"^(User|Assistant):\s*", "", clean_content, flags=re.MULTILINE).strip()
    if len(stripped_for_check) < 5:
        if lang:
            lang_display = lang.capitalize() if len(lang) > 1 else lang
            return f"{lang_display} Snippet"
        if has_code_block:
            return "Snippet"
        return "Untitled Chat"

    content = clean_content[:500]

    if title_model is None:
        return generate_fallback_title(content)
    try:
        return cast(
            str,
            await resilient_llm_call(
                primary_fn=lambda: call_llm_for_title(content, title_model),
                fallback_fn=((lambda: call_llm_for_title(content, fallback_title_model)) if fallback_title_model else None),
            ),
        )
    except Exception as exc:
        logger.error("Failed to generate chat title via LLM: %s", exc)
        return generate_fallback_title(content)
