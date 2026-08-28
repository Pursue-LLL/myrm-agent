"""Session Advisor — Tier-0 rules + Tier-1 lite model (read-only).

[INPUT]
- RunDigestStore snapshot
- User question
- Optional selection snippet
- Accept-Language for Tier-1 reply language
- core.utils.chat_utils::extract_answer_text (POS: LangChain 响应文本提取，含 reasoning 回退)

[OUTPUT]
- Advisor reply text (does not enter main agent transcript)

[POS]
Business-layer Co-Pilot side Q&A. Uses lite model SSOT from user config.
"""

from __future__ import annotations

import logging
import re

from myrm_agent_harness.utils.locale import normalize_locale

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_parsers import extract_lite_model_config
from app.core.utils.chat_utils import extract_answer_text
from app.services.agent.platform_config import load_llm_from_model_config
from app.services.copilot.run_digest_store import RunDigestStore

logger = logging.getLogger(__name__)

_STATUS_PATTERNS = re.compile(
    r"(在干嘛|在做什么|进度|状态|怎么样了|what.*doing|progress|status|running)",
    re.IGNORECASE,
)

_ADVISOR_SYSTEM_PROMPT = (
    "You are a read-only session advisor. Answer briefly about the user's active agent run. "
    "Use only the provided run context. Do not invent tool results. "
    "If context is insufficient, say what is missing. Keep answers under 120 words."
)


def _is_zh(locale: str) -> bool:
    return locale.startswith("zh")


def _advisor_system_prompt(locale: str) -> str:
    if _is_zh(locale):
        return f"{_ADVISOR_SYSTEM_PROMPT} Reply in Simplified Chinese."
    return _ADVISOR_SYSTEM_PROMPT


def _tier0_reply(question: str, digest_dict: dict[str, object], locale: str) -> str | None:
    if not _STATUS_PATTERNS.search(question.strip()):
        return None
    phase = str(digest_dict.get("phase") or "idle")
    step_count = digest_dict.get("step_count")
    pending = digest_dict.get("pending_approval_count")
    elapsed = digest_dict.get("elapsed_seconds")
    current_tool = digest_dict.get("current_tool")
    zh = _is_zh(locale)

    if phase == "waiting_approval" and isinstance(pending, int) and pending > 0:
        return f"等待审批（{pending}）" if zh else f"Waiting for your approval ({pending})"
    if phase == "running" and isinstance(step_count, int) and step_count > 0:
        tool = str(current_tool or "tool")
        return f"步骤 {step_count}：{tool}" if zh else f"Step {step_count}: {tool}"
    if phase == "completed" and isinstance(step_count, int):
        return f"已完成（{step_count} 步）" if zh else f"Finished ({step_count} steps)"
    if phase == "error":
        return "运行失败" if zh else "Run failed"
    if phase == "cancelled":
        return "运行已取消" if zh else "Run cancelled"
    headline = str(digest_dict.get("headline") or ("就绪" if zh else "Ready"))
    parts = [headline]
    if isinstance(step_count, int) and step_count > 0:
        parts.append(f"步骤: {step_count}" if zh else f"Steps: {step_count}")
    if isinstance(pending, int) and pending > 0:
        parts.append(f"待审批: {pending}" if zh else f"Pending approvals: {pending}")
    if isinstance(elapsed, int) and elapsed > 0:
        parts.append(f"已运行: {elapsed}秒" if zh else f"Elapsed: {elapsed}s")
    parts.append(f"阶段: {phase}" if zh else f"Phase: {phase}")
    return ". ".join(parts)


async def ask_advisor(
    *,
    chat_id: str,
    question: str,
    selection_snippet: str | None = None,
    accept_language: str | None = None,
) -> tuple[str, str]:
    """Return (reply, tier) where tier is 'tier0' or 'tier1'."""
    locale = normalize_locale(accept_language)
    digest = RunDigestStore.get(chat_id)
    digest_dict: dict[str, object] = digest.to_dict() if digest else {"phase": "idle", "headline": "No active run"}

    tier0 = _tier0_reply(question, digest_dict, locale)
    if tier0 is not None:
        return tier0, "tier0"

    context_lines = [
        f"Run context: {digest_dict.get('headline', '')}",
        f"Phase: {digest_dict.get('phase', 'idle')}",
        f"Steps: {digest_dict.get('step_count', 0)}",
    ]
    if selection_snippet and selection_snippet.strip():
        context_lines.append(f"Selected text: {selection_snippet.strip()[:800]}")
    context_lines.append(f"User question: {question.strip()}")

    configs = await load_user_configs()
    providers_dict = configs.providers_dict
    if not providers_dict:
        if _is_zh(locale):
            return ("未配置模型。请在设置中配置 Provider 后使用 Advisor。", "tier0")
        return (
            "No model configured. Configure a provider in Settings to use Advisor.",
            "tier0",
        )

    filter_cfg = extract_lite_model_config(providers_dict)
    model_cfg = filter_cfg or configs.model_cfg
    model_kwargs = dict(model_cfg.model_kwargs or {})
    model_kwargs["max_tokens"] = 256
    invoke_cfg = model_cfg.model_copy(
        update={"temperature": 0.2, "model_kwargs": model_kwargs},
    )

    try:
        llm = await load_llm_from_model_config(invoke_cfg, streaming=False)
        response = await llm.ainvoke(
            [
                SystemMessage(content=_advisor_system_prompt(locale)),
                HumanMessage(content="\n".join(context_lines)),
            ],
        )
        text = extract_answer_text(response).strip()
        if not text:
            if _is_zh(locale):
                return ("无法根据当前运行上下文生成回答。", "tier1")
            return ("I could not generate an answer from the current run context.", "tier1")
        return text, "tier1"
    except Exception as exc:
        logger.warning("advisor_tier1_failed: %s", exc)
        if _is_zh(locale):
            return ("Advisor 暂时不可用。请在进度面板查看运行状态。", "tier0")
        return (
            "Advisor is temporarily unavailable. Check run status in the progress panel.",
            "tier0",
        )


__all__ = ["ask_advisor"]
