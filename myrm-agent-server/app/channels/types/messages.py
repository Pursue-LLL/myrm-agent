"""Core message types: inbound, outbound, media, rendering and streaming.

[INPUT]
- channels.types.components::ComponentRow, QuickReply, ToolStep (POS: UI component types)

[OUTPUT]
- InboundMessage, OutboundMessage: inbound/outbound messages
- MediaAttachment, MediaType: media attachments
- RenderStyle, ToolSummaryDisplay: rendering configuration
- ProgressUpdate, StreamingText: streaming transport
- VoiceConfig, TTSMode, STTResult: voice configuration

[POS]
Core message type definitions. All cross-channel communication data structures
are defined here; zero I/O, pure data.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from enum import IntEnum, StrEnum

from .components import ComponentRow, QuickReply, ToolStep
from .status import ChannelCapabilities
from .thread_sharing import ThreadSharingMode


class MessagePriority(IntEnum):
    """Outbound message priority (lower value = higher priority).

    SYSTEM: approval prompts, error notifications — dispatched first.
    NORMAL: user-triggered replies — default priority.
    BULK: cron notifications, batch sends — dispatched last.
    """

    SYSTEM = 0
    NORMAL = 1
    BULK = 2


class MediaType(StrEnum):
    """Supported media attachment types for channel messages."""

    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    CONTACT = "contact"


@dataclass(frozen=True, slots=True)
class MediaAttachment:
    """A media file attached to an outbound/inbound message.

    Exactly one of ``url`` or ``path`` should be set:
    - ``url``: remote URL (channel downloads or passes through)
    - ``path``: local file path (channel reads and uploads)
    """

    media_type: MediaType
    url: str | None = None
    path: str | None = None
    filename: str | None = None
    mime_type: str | None = None
    caption: str | None = None


_IMAGE_EXTS = frozenset((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"))
_AUDIO_EXTS = frozenset((".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus"))
_VIDEO_EXTS = frozenset((".mp4", ".webm", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".m4v"))
_VCARD_MIMES = frozenset(("text/vcard", "text/x-vcard", "text/directory", "application/vcard", "application/x-vcard"))


def guess_media_type(filename: str, content_type: str | None = None) -> MediaType:
    """Infer MediaType from MIME content-type or filename extension.

    Shared utility for all channel providers to classify inbound attachments.
    MIME type takes precedence; falls back to extension matching.
    """
    ct = (content_type or "").lower()
    if ct in _VCARD_MIMES:
        return MediaType.CONTACT
    if ct.startswith("image/"):
        return MediaType.IMAGE
    if ct.startswith("audio/"):
        return MediaType.AUDIO
    if ct.startswith("video/"):
        return MediaType.VIDEO

    lower = filename.lower()
    if lower.endswith(".vcf"):
        return MediaType.CONTACT
    for ext in _IMAGE_EXTS:
        if lower.endswith(ext):
            return MediaType.IMAGE
    for ext in _AUDIO_EXTS:
        if lower.endswith(ext):
            return MediaType.AUDIO
    for ext in _VIDEO_EXTS:
        if lower.endswith(ext):
            return MediaType.VIDEO
    return MediaType.DOCUMENT


class ReasoningDisplay(StrEnum):
    """How to render LLM thinking/reasoning content in outbound messages."""

    OFF = "off"
    COLLAPSED = "collapsed"
    INLINE = "inline"


class ToolSummaryDisplay(StrEnum):
    """How to render a summary of tool calls in outbound messages."""

    OFF = "off"
    COMPACT = "compact"
    DETAILED = "detailed"


@dataclass(frozen=True, slots=True)
class RenderStyle:
    """Declares how a channel renders outbound text.

    Used by renderer.render() to format Agent output for a specific channel.
    Capability flags (supports_*) control format downgrade in the render pipeline.

    Content display flags control optional sections in the rendered output:
    - reasoning_display: how to render LLM thinking/reasoning content
    - tool_summary_display: how to render a summary of tool calls executed
    """

    format: str = "markdown"  # "markdown" | "plaintext" | "mrkdwn" | "whatsapp"
    use_emoji: bool = True
    max_text_length: int = 4000
    supports_code_fence: bool = True
    supports_links: bool = True
    supports_latex: bool = False
    supports_tables: bool = False
    app_name_prefix: str | None = None
    reasoning_display: ReasoningDisplay = ReasoningDisplay.OFF
    tool_summary_display: ToolSummaryDisplay = ToolSummaryDisplay.OFF


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    """Immutable context for cross-process lineage and distributed tracing.

    Attached to InboundMessage, inherited by ToolCalls, and bound to OutboundMessage.
    Ensures asynchronous callbacks are routed to the exact origin topic/thread,
    even if the global session drifts during long-running tasks.
    Also provides a foundation for cross-process authentication (user_id) and tracing (trace_id).
    """

    channel: str
    chat_id: str | None = None
    thread_id: str | None = None
    user_id: str | None = None
    trace_id: str | None = None
    locale: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Serialize context for cross-process transport (e.g., Celery tasks)."""
        return {
            "channel": self.channel,
            "chat_id": self.chat_id,
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "trace_id": self.trace_id,
            "locale": self.locale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | None]) -> CorrelationContext:
        """Deserialize context from cross-process transport."""
        return cls(
            channel=str(data.get("channel", "")),
            chat_id=data.get("chat_id"),
            thread_id=data.get("thread_id"),
            user_id=data.get("user_id"),
            trace_id=data.get("trace_id"),
            locale=data.get("locale"),
        )

    def create_reply(
        self,
        content: str,
        *,
        metadata: dict[str, object] | None = None,
        media: tuple[MediaAttachment, ...] = (),
        reply_to_id: str | None = None,
        reasoning: str | None = None,
        tool_steps: tuple[ToolStep, ...] = (),
        components: tuple[ComponentRow, ...] = (),
        quick_replies: tuple[QuickReply, ...] = (),
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> OutboundMessage:
        """Create an OutboundMessage precisely routed back to this context's origin.

        This is the recommended way for business logic to send asynchronous callbacks,
        as it guarantees the message will reach the exact channel/chat/thread that
        triggered the original task, preventing routing drift.
        """
        merged_metadata: dict[str, object] = dict(metadata) if metadata else {}
        if self.locale and "locale" not in merged_metadata:
            merged_metadata["locale"] = self.locale

        return OutboundMessage(
            channel=self.channel,
            recipient_id=self.chat_id or "",
            content=content,
            user_id=self.user_id or "",
            metadata=merged_metadata or None,
            media=media,
            reply_to_id=reply_to_id,
            thread_id=self.thread_id,
            reasoning=reasoning,
            tool_steps=tool_steps,
            components=components,
            quick_replies=quick_replies,
            priority=priority,
            correlation_context=self,
        )


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    """Message flowing from the system to an external channel.

    Produced by: Cron executor, Agent runtime, system notifications.
    Consumed by: Channel providers (ChatChannel, TelegramChannel, etc.).

    ``components``: interactive buttons/selects attached to the message.
    ``quick_replies``: quick-reply chips (tap → send text message).
    Channels that don't support native components will receive a
    text fallback appended to ``content`` by the Router.

    Cron-specific context (job_name, success) is carried in ``metadata``
    and extracted via ``extract_cron_context(msg)``.
    """

    channel: str
    recipient_id: str
    content: str
    user_id: str
    metadata: dict[str, object] | None = None
    media: tuple[MediaAttachment, ...] = ()
    reply_to_id: str | None = None
    thread_id: str | None = None
    reasoning: str | None = None
    tool_steps: tuple[ToolStep, ...] = ()
    components: tuple[ComponentRow, ...] = ()
    quick_replies: tuple[QuickReply, ...] = ()
    priority: MessagePriority = MessagePriority.NORMAL
    correlation_context: CorrelationContext | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the message to a JSON-compatible dictionary."""
        import dataclasses

        def _serialize(obj: object) -> object:
            if dataclasses.is_dataclass(obj):
                d = {k: _serialize(v) for k, v in dataclasses.asdict(obj).items()}
                d["__type__"] = obj.__class__.__name__
                return d
            elif isinstance(obj, (list, tuple)):
                return [_serialize(i) for i in obj]
            elif isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            elif hasattr(obj, "value"):  # Enum
                return obj.value
            return obj

        return _serialize(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> OutboundMessage:
        """Deserialize the message from a dictionary."""
        from .components import (
            ActionButton,
            ButtonStyle,
            QuickReply,
            SelectMenu,
            SelectOption,
            ToolStep,
        )

        def _deserialize_media(m_data: dict[str, object]) -> MediaAttachment:
            return MediaAttachment(
                media_type=MediaType(m_data["media_type"]),
                url=m_data.get("url"),
                path=m_data.get("path"),
                filename=m_data.get("filename"),
                mime_type=m_data.get("mime_type"),
                caption=m_data.get("caption"),
            )

        def _deserialize_component(
            c_data: dict[str, object],
        ) -> ActionButton | SelectMenu:
            ctype = c_data.get("__type__")
            if ctype == "ActionButton":
                return ActionButton(
                    label=c_data["label"],
                    action_id=c_data["action_id"],
                    style=ButtonStyle(c_data.get("style", "default")),
                    value=c_data.get("value", ""),
                    url=c_data.get("url", ""),
                )
            elif ctype == "SelectMenu":
                options = tuple(SelectOption(**o) for o in c_data.get("options", []))
                return SelectMenu(
                    action_id=c_data["action_id"],
                    placeholder=c_data["placeholder"],
                    options=options,
                )
            raise ValueError(f"Unknown component type: {ctype}")

        media = tuple(_deserialize_media(m) for m in data.get("media", []))
        tool_steps = tuple(
            ToolStep(name=t.get("name", ""), label=t.get("label", ""), detail=t.get("detail")) for t in data.get("tool_steps", [])
        )

        components = []
        for row_data in data.get("components", []):
            row = tuple(_deserialize_component(c) for c in row_data)
            components.append(row)

        quick_replies = tuple(
            QuickReply(label=q["label"], text=q["text"], required=q.get("required", False)) for q in data.get("quick_replies", [])
        )

        corr_data = data.get("correlation_context")
        correlation_context = CorrelationContext(**{k: v for k, v in corr_data.items() if k != "__type__"}) if corr_data else None

        return cls(
            channel=data["channel"],
            recipient_id=data["recipient_id"],
            content=data["content"],
            user_id=data["user_id"],
            metadata=data.get("metadata"),
            media=media,
            reply_to_id=data.get("reply_to_id"),
            thread_id=data.get("thread_id"),
            reasoning=data.get("reasoning"),
            tool_steps=tool_steps,
            components=tuple(components),
            quick_replies=quick_replies,
            priority=MessagePriority(data.get("priority", MessagePriority.NORMAL.value)),
            correlation_context=correlation_context,
        )

    def strip_media(self, placeholder: str = "\n\n[Image/FileSendFailure，Only保留text]") -> OutboundMessage:
        """Return a new message with media stripped and a placeholder appended."""
        if not self.media:
            return self

        new_content = self.content
        if new_content:
            new_content += placeholder
        else:
            new_content = placeholder.strip()

        return replace(self, media=(), content=new_content)


@dataclass(frozen=True, slots=True)
class CronContext:
    """Cron-specific delivery context extracted from OutboundMessage.metadata."""

    job_name: str
    success: bool


def extract_cron_context(msg: OutboundMessage) -> CronContext | None:
    """Extract cron delivery context from message metadata, if present."""
    meta = msg.metadata
    if not meta:
        return None
    job_name = meta.get("job_name")
    success = meta.get("success")
    if isinstance(job_name, str) and isinstance(success, bool):
        return CronContext(job_name=job_name, success=success)
    return None


@dataclass(frozen=True, slots=True)
class ContextEntry:
    """A single non-trigger message preserved for group context accumulation.

    Stored by GroupContextBuffer, injected into InboundMessage when triggered.
    """

    sender_id: str
    content: str
    timestamp: float
    sender_name: str | None = None


@dataclass(frozen=True, slots=True)
class ReplyContext:
    """Structured reply/quote context for replied-to messages.

    Provides complete context of the message being replied to or quoted,
    enabling LLMs to understand reply relationships without text flattening.

    Supported channels: WeCom (quote), Telegram (reply_to_message),
    Feishu (parent_id), Discord (reference), Slack (thread_ts).
    """

    message_id: str
    content: str
    media: tuple[MediaAttachment, ...] = ()
    sender_id: str | None = None
    sender_name: str | None = None
    timestamp: float | None = None


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """Message flowing from an external channel into the system.

    Produced by: Channel providers (TelegramChannel, FeishuChannel, etc.).
    Consumed by: AgentRouter via MessageBus.

    ``resume_value`` is set for approval commands (/approve, /deny) to resume
    an interrupted Agent with the user's decision. When non-None, the router
    converts it to ``Command(resume=...)`` for LangGraph.

    Time Semantics:
        - ``sent_at``: User's actual send time (Unix timestamp, float seconds).
        - ``sent_timezone``: IANA timezone string (e.g., "Asia/Shanghai") when the message was sent.
        These fields enable deterministic timestamp rendering for Prompt Cache stability.
    """

    channel: str
    sender_id: str
    content: str
    sent_at: float = field(default_factory=time.time)
    sent_timezone: str = "UTC"
    chat_id: str | None = None
    user_id: str | None = None
    sender_name: str | None = None
    is_group: bool = False
    is_bot: bool = False
    mentioned: bool = False
    media: tuple[MediaAttachment, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)
    reply_to_id: str | None = None
    thread_id: str | None = None
    context_messages: tuple[ContextEntry, ...] = ()
    message_id: str | None = None
    resume_value: dict[str, object] | None = None
    reply_to: ReplyContext | None = None  # Structured reply/quote context
    correlation_context: CorrelationContext | None = None
    channel_capabilities: ChannelCapabilities | None = None

    def get_or_create_correlation_context(self) -> CorrelationContext:
        """Return the existing correlation context or create a new one from message attributes."""
        if self.correlation_context:
            return self.correlation_context
        locale_val = None
        if self.metadata and self.metadata.get("locale"):
            locale_val = str(self.metadata["locale"])
        return CorrelationContext(
            channel=self.channel,
            chat_id=self.chat_id,
            thread_id=self.thread_id,
            user_id=self.user_id,
            locale=locale_val,
        )


@dataclass(frozen=True, slots=True)
class TopicContext:
    """Per-topic configuration for forum-style thread routing.

    When a message arrives from a forum topic (e.g. Telegram supergroup topic),
    this context carries topic-specific overrides that affect session isolation
    and Agent selection.

    ``thread_sharing_mode``: Controls chat history visibility within a thread.
    - ``isolated`` (default): Each user has their own conversation history.
    - ``shared``: All users in the thread share the same conversation history,
      enabling collaborative scenarios (Discord Forum, Telegram Forum Topics).
    """

    topic_id: str
    agent_id: str | None = None
    enabled: bool = True
    bound_at: str | None = None
    matched_by: str | None = None
    thread_sharing_mode: ThreadSharingMode = ThreadSharingMode.ISOLATED


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """A human-readable progress label emitted during Agent execution.

    Yielded by AgentExecutor.execute_stream() between tool calls.
    Consumed by AgentRouter to edit Placeholder messages in real-time.

    When ``quick_replies`` is non-empty, the Router sends them alongside
    the progress text — enabling interactive prompts like tool approval
    buttons in IM channels.
    """

    label: str
    quick_replies: tuple[QuickReply, ...] = ()


@dataclass(frozen=True, slots=True)
class FissionTopologyNode:
    """Represents a single subagent node in a Fission topology map."""

    node_id: str
    agent_type: str
    objective: str
    status: str  # "pending", "running", "completed", "failed", "paused"
    error: str | None = None
    cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class FissionTopologyUpdate:
    """A structured update for a Swarm Fission topology map.

    Yielded by AgentExecutor.execute_stream() when subagents spawn, update status, or complete.
    Consumed by Frontend GUI to render a React Flow DAG representing the parallel task execution.
    """

    fission_id: str
    nodes: tuple[FissionTopologyNode, ...]
    total_cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class StreamingText:
    """Accumulated streaming text snapshot emitted during answer generation.

    Yielded by AgentExecutor.execute_stream() as the LLM generates tokens.
    Consumed by AgentRouter to progressively edit Placeholder messages,
    giving users real-time visibility into the response being generated.
    The ``text`` field contains the full accumulated text (not a delta).
    """

    text: str


# ---------------------------------------------------------------------------
# Voice STT/TTS types
# ---------------------------------------------------------------------------


class TTSMode(StrEnum):
    """Controls when Agent replies are converted to audio."""

    OFF = "off"
    ALWAYS = "always"
    INBOUND = "inbound"


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    """Combined STT + TTS configuration injected by the business layer.

    STT: transcribes inbound voice messages to text before Agent processing.
    TTS: converts Agent text replies to audio before sending.
    """

    stt_enabled: bool = False
    stt_provider: str = "openai"
    stt_api_key: str = ""
    stt_model: str = "whisper-1"
    stt_language: str | None = None

    stt_local_model: str = "base"
    stt_local_device: str = "auto"
    stt_local_compute_type: str = "auto"
    stt_base_url: str = ""

    tts_mode: TTSMode = TTSMode.OFF
    tts_provider: str = "edge"
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_voice: str = ""
    tts_speed: float = 1.0
    tts_pitch: float = 0.0
    tts_max_length: int = 4000

    tts_summary_enabled: bool = True
    tts_summary_threshold: int = 1500
    tts_summary_model: str = ""


@dataclass(frozen=True, slots=True)
class STTResult:
    """Result of speech-to-text transcription."""

    text: str
    language: str | None = None
    duration: float | None = None
