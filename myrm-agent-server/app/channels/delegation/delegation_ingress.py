"""Ingress parsing, intent detection, and immediate receipt generation for mobile task delegation.

Inspects inbound messages from mobile IM channels (WeChat, Feishu, DingTalk,
Telegram, Slack, Discord) to identify long-running offline delegation intents,
guarantees sub-second receipt generation, and prevents duplicate active delegations.

[INPUT]
- InboundMessage or raw text strings, channel identifiers, and user metadata.
- .delegation_models::DelegationTask, DelegationReceipt, DelegationStatus

[OUTPUT]
- is_delegation_intent: Heuristic and explicit classifier for long-running tasks.
- build_delegation_task: Factory initializing persistent DelegationTask entity.
- build_receipt_card_content: Render structured acknowledgement for mobile chat.
- DelegationIngressGuard: Session-scoped concurrency and anti-duplicate manager.

[POS]
Channel ingress gateway for asynchronous cross-platform task delegation.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from .delegation_models import DelegationReceipt, DelegationStatus, DelegationTask

if TYPE_CHECKING:
    pass

_EXPLICIT_DELEGATION_PREFIXES: tuple[str, ...] = (
    "/delegate",
    "/async",
    "/btw",
    "/background",
    "/bg",
    "【委派】",
    "【后台任务】",
    "【异步任务】",
)

_LONG_RUNNING_INTENT_KEYWORDS: tuple[str, ...] = (
    "做成ppt",
    "生成ppt",
    "生成报表",
    "做个excel",
    "深度调研",
    "全量重构",
    "排查代码",
    "批量审批",
    "分析竞品",
    "整理文档",
    "通宵跑",
    "明早给我",
    "在后台干",
    "做成网页",
    "全网爬取",
    "generate ppt",
    "deep research",
    "full refactor",
    "run overnight",
)

_IMMEDIATE_FAST_QUERY_PATTERNS: tuple[str, ...] = (
    "天气",
    "几点",
    "星期几",
    "你好",
    "hi",
    "hello",
    "谁是",
    "翻译一下",
    "1+1",
    "算一下",
)


def is_delegation_intent(text: str, *, explicit_only: bool = False) -> tuple[bool, float, str]:
    """Classify whether inbound text conveys an asynchronous delegation intent.

    Args:
        text: Raw user message string.
        explicit_only: If True, only match explicit command prefixes.

    Returns:
        (is_delegated, confidence_score, extracted_clean_prompt)
    """
    cleaned = text.strip()
    if not cleaned:
        return False, 0.0, ""

    # 1. Check explicit command prefixes (100% confidence)
    for prefix in _EXPLICIT_DELEGATION_PREFIXES:
        if cleaned.lower().startswith(prefix.lower()):
            clean_prompt = cleaned[len(prefix) :].strip().lstrip(":：- ")
            return True, 1.0, clean_prompt

    if explicit_only:
        return False, 0.0, cleaned

    # 2. Fast query negative bypass (prevent false positives on simple queries)
    lower_text = cleaned.lower()
    if len(cleaned) < 30:
        for fast_kw in _IMMEDIATE_FAST_QUERY_PATTERNS:
            if fast_kw in lower_text:
                return False, 0.0, cleaned

    # 3. Heuristic scoring for natural language long tasks
    score = 0.0
    matched_kws: list[str] = []
    for kw in _LONG_RUNNING_INTENT_KEYWORDS:
        if kw in lower_text:
            score += 0.45
            matched_kws.append(kw)

    # Text length and multi-step indication booster
    if len(cleaned) > 50:
        score += 0.2
    if any(sep in cleaned for sep in ("第一步", "然后", "接着", "最后", "并且", "同时")):
        score += 0.25

    is_delegated = score >= 0.85
    return is_delegated, min(1.0, score), cleaned


def build_delegation_task(
    origin_channel: str,
    origin_user_id: str,
    origin_chat_id: str,
    raw_prompt: str,
    normalized_prompt: str,
    *,
    timeout_seconds: float = 3600.0,
) -> DelegationTask:
    """Create a persistent DelegationTask instance with global unique ID."""
    task_id = f"tsk_{uuid.uuid4().hex[:12]}"
    return DelegationTask(
        task_id=task_id,
        origin_channel=origin_channel,
        origin_user_id=origin_user_id,
        origin_chat_id=origin_chat_id,
        raw_prompt=raw_prompt,
        normalized_prompt=normalized_prompt,
        status=DelegationStatus.PENDING,
        timeout_seconds=timeout_seconds,
    )


def build_receipt_card_content(receipt: DelegationReceipt, *, platform: str = "default") -> str:
    """Build user-facing immediate acknowledgment text or Markdown card.

    Args:
        receipt: Generated DelegationReceipt.
        platform: Target channel identifier for platform-specific rendering.

    Returns:
        Structured user-friendly acknowledgement string.
    """
    est_mins = max(1, receipt.estimated_duration_seconds // 60)
    lines = [
        "🤖 **任务已委派至后台沙箱自主接管**",
        f"• **任务编号**：`{receipt.task_id}`",
        f"• **当前状态**：{receipt.status.value}",
        f"• **预估耗时**：约 {est_mins} 分钟",
        "• **执行说明**：您可以锁屏或处理其他事务。执行完毕后，生成的交付物（PPT/报表/文档）将自动在此向您推送。",
    ]
    if receipt.tracking_deep_link:
        lines.append(f"• **实时看板**：[点击查看执行轨迹]({receipt.tracking_deep_link})")

    return "\n".join(lines)


class DelegationIngressGuard:
    """Manages active delegation concurrency per (channel, user_id) tuple."""

    def __init__(self, max_active_per_user: int = 3) -> None:
        self.max_active = max_active_per_user
        # (channel, user_id) -> list of active task_ids
        self._user_active_tasks: dict[tuple[str, str], list[str]] = {}

    def can_delegate(self, channel: str, user_id: str) -> bool:
        """Check whether the user is within concurrent active task quota."""
        active = self._user_active_tasks.get((channel, user_id), [])
        return len(active) < self.max_active

    def register_active_task(self, channel: str, user_id: str, task_id: str) -> None:
        """Register a new active task for the user."""
        key = (channel, user_id)
        if key not in self._user_active_tasks:
            self._user_active_tasks[key] = []
        if task_id not in self._user_active_tasks[key]:
            self._user_active_tasks[key].append(task_id)

    def release_task(self, channel: str, user_id: str, task_id: str) -> None:
        """Release completed or failed task from active tracker."""
        key = (channel, user_id)
        if key in self._user_active_tasks:
            self._user_active_tasks[key] = [
                tid for tid in self._user_active_tasks[key] if tid != task_id
            ]
            if not self._user_active_tasks[key]:
                self._user_active_tasks.pop(key, None)

    def get_latest_active_task(self, channel: str, user_id: str) -> str | None:
        """Get the most recent active task_id for in-flight steering."""
        active = self._user_active_tasks.get((channel, user_id), [])
        return active[-1] if active else None
