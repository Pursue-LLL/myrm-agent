"""Ingress parsing and intent detection for mobile task delegation.

Inspects inbound messages from mobile IM channels (WeChat, Feishu, DingTalk,
Telegram, Slack, Discord) to identify long-running offline delegation intents
and caps the number of delegations a user can have running at once.

[INPUT]
- Raw message text strings, channel identifiers, and user ids.
- .delegation_models::DelegationTask, DelegationStatus

[OUTPUT]
- is_delegation_intent: Heuristic and explicit classifier for long-running tasks.
- build_delegation_task: Factory initializing persistent DelegationTask entity.
- DelegationIngressGuard: Per-user cap on concurrently running delegations.

[POS]
Channel ingress gateway for asynchronous cross-platform task delegation.
"""

from __future__ import annotations

import uuid

from .delegation_models import DelegationStatus, DelegationTask

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
    prompt: str,
    *,
    timeout_seconds: float = 3600.0,
) -> DelegationTask:
    """Create a pending DelegationTask with a unique ID."""
    return DelegationTask(
        task_id=f"tsk_{uuid.uuid4().hex[:12]}",
        origin_channel=origin_channel,
        origin_user_id=origin_user_id,
        origin_chat_id=origin_chat_id,
        prompt=prompt,
        status=DelegationStatus.PENDING,
        timeout_seconds=timeout_seconds,
    )


class DelegationIngressGuard:
    """Manages active delegation concurrency per (channel, user_id) tuple."""

    def __init__(self, max_active_per_user: int = 2) -> None:
        self.max_active = max_active_per_user
        # (channel, user_id) -> list of active task_ids
        self._user_active_tasks: dict[tuple[str, str], list[str]] = {}

    def can_accept(self, channel: str, user_id: str) -> bool:
        """Check whether the user is within concurrent active task quota."""
        active = self._user_active_tasks.get((channel, user_id), [])
        return len(active) < self.max_active

    def acquire(self, channel: str, user_id: str, task_id: str) -> None:
        """Register a new active task for the user."""
        key = (channel, user_id)
        if key not in self._user_active_tasks:
            self._user_active_tasks[key] = []
        if task_id not in self._user_active_tasks[key]:
            self._user_active_tasks[key].append(task_id)

    def release(self, channel: str, user_id: str, task_id: str) -> None:
        """Release completed or failed task from active tracker."""
        key = (channel, user_id)
        if key in self._user_active_tasks:
            self._user_active_tasks[key] = [tid for tid in self._user_active_tasks[key] if tid != task_id]
            if not self._user_active_tasks[key]:
                self._user_active_tasks.pop(key, None)
