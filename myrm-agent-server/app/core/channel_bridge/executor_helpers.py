"""Helper functions for ChannelAgentExecutor.

Post-execution tasks: history persistence, title generation, approval timeout
scheduling, stream accumulation, and channel notifications.

[INPUT]
- app.services.chat.chat_service::ChatService (POS: Chat history persistence)
- app.services.agent.approval_timeout_scheduler (POS: Approval timeout scheduling)
- app.core.channel_bridge.config_loader (POS: User config extraction)
- myrm_agent_harness.utils.text_utils::strip_internal_markers (POS: Output sanitization)

[OUTPUT]
- build_chat_history_with_metadata: Convert history entries to framework format
- persist_and_load_history: Persist user message + load chat history
- load_history_without_persist: Load history for resume flows
- persist_assistant_message: Save assistant response
- generate_channel_title: LLM-powered title generation
- schedule_channel_approval_timeout: Register approval timeout guard
- notify_channel_timeout_result: Send timeout notification to channel
- extract_external_agents: Extract agents from UserConfig
- suggest_quick_replies: Generate contextual quick-reply suggestions
- step_to_label: Translate Agent step_key to progress label
- StreamAccumulator: Lightweight response accumulator

[POS]
ChannelAgentExecutor 的辅助模块。处理执行前后的持久化、超时调度、
流式累积等关注点，使主执行器保持精简。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.utils.coercion import parse_float
from myrm_agent_harness.utils.text_utils import strip_internal_markers

from app.channels.types import (
    OutboundMessage,
    QuickReply,
    ToolStep,
)

if TYPE_CHECKING:
    from app.services.chat.chat_service import ChannelHistoryEntry

logger = logging.getLogger(__name__)


_STEP_LABELS: dict[str, str] = {
    "web_search_tool": "🔍 Searching the web...",
    "reviewing_sources": "📖 Reviewing sources...",
    "code_interpreter_tool": "💻 Running code...",
    "bash_code_execute_tool_tool": "🖥️ Executing command...",
    "file_read_tool": "📄 Reading file...",
    "file_write_tool": "📝 Writing file...",
    "file_edit_tool": "✏️ Editing file...",
}


def build_chat_history_with_metadata(
    entries: list[ChannelHistoryEntry],
) -> list[list[str | object]]:
    """Convert structured history entries to framework chat_history format.

    For user messages, attaches {ts: ISO8601} metadata so the framework layer
    can inject deterministic timestamps (handled by BaseAgent.run()).
    """
    history: list[list[str | object]] = []
    for entry in entries:
        if entry.role == "human":
            history.append(["human", entry.content, {"ts": entry.created_at.isoformat()}])
        else:
            history.append(["assistant", entry.content])
    return history


async def persist_and_load_history(
    channel_session_key: str,
    source: str,
    content: str,
    sent_at: datetime,
    sent_timezone: str,
    agent_id: str | None = None,
) -> tuple[str, list[ChannelHistoryEntry]]:
    """Persist the user message and load chat history in a single DB session.

    Returns (chat_id, history_entries) where history_entries excludes the current message.
    Each entry carries sent_at for deterministic timestamp injection.

    Args:
        sent_at: User's actual send time (UTC datetime).
        sent_timezone: IANA timezone string when message was sent.
    """
    from app.database.connection import get_session
    from app.services.chat.chat_service import ChatService

    async with get_session() as session:
        chat = await ChatService.get_or_create_channel_chat(
            channel_session_key,
            source,
            agent_id=agent_id,
        )
        await ChatService.append_message(chat.id, "user", content, sent_at, sent_timezone)
        history = await ChatService.load_channel_history(chat.id, api_key=None)
        await session.commit()
        logger.warning(
            "Channel chat persisted: chat_id=%s, history_len=%d",
            chat.id,
            len(history),
        )
        return chat.id, history


async def load_history_without_persist(
    channel_session_key: str,
) -> tuple[str, list[ChannelHistoryEntry]]:
    """Load chat history without persisting any new message (for resume operations).

    Used when resuming an interrupted agent via /approve or /deny commands.
    The resume message itself should not be saved to chat history.

    Returns (chat_id, history_entries) for the existing session.
    """
    from app.database.connection import get_session
    from app.services.chat.chat_service import ChatService

    async with get_session() as _session:
        chat = await ChatService.get_channel_chat_by_key(channel_session_key)
        if not chat:
            logger.warning(
                "Resume attempted but no chat found for session_key=%s user=%s",
                channel_session_key,
            )
            return "", []

        history = await ChatService.load_channel_history(chat.id, api_key=None)
        logger.warning(
            "Resume: loaded history for chat_id=%s, history_len=%d",
            chat.id,
            len(history),
        )
        return chat.id, history


async def persist_assistant_message(chat_id: str, content: str, timezone: str | None = None) -> None:
    """Persist the assistant's response after Agent completes.

    Args:
        timezone: User timezone (optional, defaults to UTC).
    """
    from datetime import datetime
    from datetime import timezone as tz_module

    from app.database.connection import get_session
    from app.services.chat.chat_service import ChatService

    async with get_session() as session:
        sent_at = datetime.now(tz=tz_module.utc)
        sent_timezone = timezone or "UTC"
        await ChatService.append_message(chat_id, "assistant", content, sent_at, sent_timezone)
        await session.commit()


async def generate_channel_title(
    chat_id: str,
    first_message: str,
    lite_model_cfg: object | None,
) -> None:
    """Generate an LLM-powered title for a new channel chat (fire-and-forget).

    Falls back to truncated first message if no filter model is configured.
    """
    from app.database.connection import get_session
    from app.database.dto import _TitleModelConfig
    from app.services.chat.chat_service import ChatService

    try:
        title_model: _TitleModelConfig | None = None
        if lite_model_cfg is not None:
            from app.core.types import ModelConfig

            if isinstance(lite_model_cfg, ModelConfig):
                title_model = _TitleModelConfig.model_validate(
                    {
                        "model": lite_model_cfg.model,
                        "apiKey": lite_model_cfg.api_key,
                        "baseUrl": lite_model_cfg.base_url,
                    }
                )

        if title_model:
            title = await ChatService._call_llm_for_title(first_message[:200], title_model)
        else:
            title = ChatService._generate_fallback_title(first_message)

        async with get_session() as _session:
            await ChatService.update_chat_title(chat_id, title)
    except Exception:
        logger.warning("Failed to generate channel chat title for %s", chat_id)


def schedule_channel_approval_timeout(
    channel: str,
    peer: str,
    chat_id: str,
    timeout_info: dict[str, object],
    params: object,
) -> None:
    """Register a backend timeout guard for a channel approval request.

    On timeout, creates a new Agent instance and executes the resume flow.
    Results are persisted to DB; the user sees them in the next interaction.
    """
    timeout_seconds = parse_float(timeout_info.get("seconds", 300), 300.0)
    behavior = str(timeout_info.get("behavior", "deny"))
    scheduler_key = f"{channel}:{peer}"

    async def resume_callback(resume_value: dict[str, object]) -> None:
        from langgraph.types import Command

        from app.ai_agents.agents import AgentFactory, GeneralAgentParams

        if not isinstance(params, GeneralAgentParams):
            logger.error("Channel timeout resume: unexpected params type: %s", type(params))
            return

        resume_params = params.model_copy()
        resume_params.query = Command(resume=resume_value)

        agent = AgentFactory.create_general_agent(resume_params)
        try:
            chat_history = build_chat_history_with_metadata((await load_history_without_persist(f"{channel}:{peer}"))[1])
            chunks: list[str] = []
            next_timeout: dict[str, object] | None = None
            async for event in agent.process_stream(
                query=resume_params.query,
                chat_history=chat_history or None,
                chat_id=chat_id,
            ):
                event_type = event.get("type", "")
                if event_type == "message" and isinstance(event.get("data"), str):
                    chunks.append(str(event["data"]))
                elif event_type == "tool_approval_request":
                    data = event.get("data", {})
                    if isinstance(data, dict):
                        extensions = data.get("extensions", {})
                        timeout_ext = extensions.get("timeout", {}) if isinstance(extensions, dict) else {}
                        if isinstance(timeout_ext, dict):
                            next_timeout = {
                                "seconds": timeout_ext.get("seconds", 300),
                                "behavior": timeout_ext.get("behavior", "deny"),
                            }

            content = strip_internal_markers("".join(chunks))
            if content.strip():
                await persist_assistant_message(chat_id, content)

            decisions = resume_value.get("decisions")
            decision = decisions[0].get("type", "reject") if isinstance(decisions, list) and decisions else "reject"
            await notify_channel_timeout_result(
                channel,
                peer,
                decision,
                content.strip() or None,
            )

            if next_timeout:
                schedule_channel_approval_timeout(
                    channel=channel,
                    peer=peer,
                    chat_id=chat_id,
                    timeout_info=next_timeout,
                    params=resume_params,
                )
            else:
                logger.info(
                    "Channel timeout auto-resume completed: key=%s, chat_id=%s",
                    scheduler_key,
                    chat_id,
                )
        finally:
            await agent.close()

    ApprovalTimeoutScheduler.get().schedule(
        key=scheduler_key,
        timeout_seconds=timeout_seconds,
        behavior=behavior,
        resume_callback=resume_callback,
    )


async def notify_channel_timeout_result(
    channel: str,
    peer: str,
    decision: str,
    agent_response: str | None,
) -> None:
    """Send a notification to the channel after an approval timeout auto-resume.

    Informs the user what decision was made and includes the Agent's response
    (if any) so the user doesn't have to check the chat history.
    """
    from app.core.channel_bridge import channel_gateway

    action = "approved" if decision == "approve" else "denied"
    parts = [f"⏱ Approval timed out — auto-{action}."]
    if agent_response:
        parts.append(agent_response)
    content = "\n\n".join(parts)

    try:
        await channel_gateway.publish(
            OutboundMessage(
                channel=channel,
                recipient_id=peer,
                content=content,
            )
        )
    except Exception:
        logger.warning(
            "Failed to send timeout notification to channel=%s peer=%s",
            channel,
            peer,
        )


_FIRST_MESSAGE_QUICK_REPLIES: tuple[QuickReply, ...] = (
    QuickReply(label="🔍 Search the web", text="Search for the latest news"),
    QuickReply(label="💻 Write code", text="Help me write code"),
    QuickReply(label="📝 Summarize", text="Summarize a document for me"),
)


def extract_external_agents(
    external_agents_dict: dict[str, object] | None,
) -> list[dict[str, object]] | None:
    """Extract agents list from UserConfig 'externalAgents' dict."""
    if not external_agents_dict:
        return None
    agents_list = external_agents_dict.get("agents")
    if isinstance(agents_list, list):
        return agents_list
    return None


def suggest_quick_replies(*, is_first_message: bool) -> tuple[QuickReply, ...]:
    """Generate contextual quick-reply suggestions.

    Currently only emits static suggestions for the first message in a new
    session. Future enhancement: use filter model for dynamic suggestions.
    """
    if is_first_message:
        return _FIRST_MESSAGE_QUICK_REPLIES
    return ()


def step_to_label(step_key: str, event: dict[str, object]) -> str | None:
    """Translate an Agent step_key into a human-readable progress label."""
    if step_key.endswith("_tool_error"):
        return "⚠️ Tool error, retrying..."

    label = _STEP_LABELS.get(step_key)
    if label and step_key == "reviewing_sources":
        count = event.get("count")
        if isinstance(count, int) and count > 0:
            return f"📖 Reviewing {count} sources..."
    return label


@dataclass
class StreamAccumulator:
    """Lightweight accumulator for channel agent responses."""

    chunks: list[str] = field(default_factory=list)
    reasoning_chunks: list[str] = field(default_factory=list)
    tool_steps: list[ToolStep] = field(default_factory=list)
    sources: list[dict[str, object]] = field(default_factory=list)
    error_message: str | None = None
    last_image_base64: str | None = None
    last_image_mime: str = "image/jpeg"
    last_image_tool: str = ""
    _seen: set[int] = field(default_factory=set)

    def add_sources(self, items: list[dict[str, object]]) -> None:
        for src in items:
            idx = src.get("index")
            if isinstance(idx, int) and idx not in self._seen:
                self._seen.add(idx)
                self.sources.append(src)
