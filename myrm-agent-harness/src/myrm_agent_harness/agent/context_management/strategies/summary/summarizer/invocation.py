"""[INPUT]
- myrm_agent_harness.agent.config.llm_safety::normalize_messages (POS: Provider safety normalization. Pure function for direct LLM paths; agent middleware covers the primary runtime.)
- myrm_agent_harness.agent.security.detection.leak_detector::redact_leaks (POS: Leak detector — re-exported from core.security.detection.leak_detector.)
- myrm_agent_harness.agent.security.detection.pii_redactor::redact_pii (POS: PII redactor. Type-aware smart masking (phone numbers retain first 3 and last 4 digits, emails retain domain, cards and IBANs their last 4 characters, etc.) for user-friendly redaction, applied for the levels the caller names, so one level's redaction never masks another level's content.)
- myrm_agent_harness.core.thinking_blocks::without_thinking_blocks (POS: drops the signed reasoning a call under another prompt cannot replay)
- myrm_agent_harness.utils.logger_utils::get_agent_logger (POS: Unified logging utilities. Provides consistent log format and convenience methods (step/success/error_detail) for project-wide log output.)
- myrm_agent_harness.agent.context_management.infra.schemas::StructuredSummary (POS: Context management shared data structures. Defines compact format types, summary schemas, and configuration constants as)
- myrm_agent_harness.agent.context_management.strategies.summary.progress_timeout::ProgressClock / SummaryProgressTracker (POS: Progress-aware timeout primitives for summarization. Decouples timeout detection from LLM invocation, allowing watchdog coroutines to observe liveness without coupling to specific streaming implementations.)
- myrm_agent_harness.agent.context_management.strategies.summary.summary_parser::_build_summary_from_dict / parse_summary_response (POS: Summary parsing and message formatting utilities.)

[OUTPUT]
- _FallbackSummaryModel: _FallbackSummaryModel
- _get_structured_llm_or_parser: _get_structured_llm_or_parser
- _redact_summary_fields: Apply credential and PII redaction to all text fields of a StructuredSummary.
- _coerce_to_structured_summary: Normalize ``with_structured_output``/parser output into a ``StructuredSummary``.
- _invoke_summary: _invoke_summary
- _stream_with_progress: Stream LLM response token-by-token, calling tracker.touch() on each chunk.
- _build_summary_invocation_messages: _build_summary_invocation_messages

[POS]
摘要策略子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from myrm_agent_harness.agent.config.llm_safety import normalize_messages
from myrm_agent_harness.agent.security.detection.leak_detector import redact_leaks
from myrm_agent_harness.agent.security.detection.pii_redactor import redact_pii
from myrm_agent_harness.core.thinking_blocks import without_thinking_blocks
from myrm_agent_harness.utils.logger_utils import get_agent_logger

from ....infra.schemas import StructuredSummary
from ..progress_timeout import (
    ProgressClock,
    SummaryProgressTracker,
)
from ..summary_parser import (
    _build_summary_from_dict,
    parse_summary_response,
)

logger = get_agent_logger(__name__)


class _FallbackSummaryModel(BaseModel):
    user_goal: str = Field(default="")
    completed_actions: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    errors_and_fixes: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    last_action: str = Field(default="")
    context_dump_path: str = Field(default="")
    active_task: str = Field(default="")
    constraints_and_preferences: list[str] = Field(default_factory=list)
    resolved_questions: list[str] = Field(default_factory=list)
    pending_user_asks: list[str] = Field(default_factory=list)
    active_state: str = Field(default="")
    blocked_items: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)

    def to_structured_summary(self) -> StructuredSummary:
        return StructuredSummary(
            user_goal=self.user_goal,
            completed_actions=self.completed_actions,
            key_findings=self.key_findings,
            errors_and_fixes=self.errors_and_fixes,
            files_modified=self.files_modified,
            last_action=self.last_action,
            context_dump_path=self.context_dump_path,
            active_task=self.active_task,
            constraints_and_preferences=self.constraints_and_preferences,
            resolved_questions=self.resolved_questions,
            pending_user_asks=self.pending_user_asks,
            active_state=self.active_state,
            blocked_items=self.blocked_items,
            next_steps=self.next_steps,
        )


def _get_structured_llm_or_parser(
    llm: BaseChatModel,
) -> tuple[object | None, PydanticOutputParser[_FallbackSummaryModel] | None]:
    try:
        structured_llm = llm.with_structured_output(StructuredSummary)
        return structured_llm, None
    except NotImplementedError:
        logger.warning(" Model does not support with_structured_output natively, degrading to PydanticOutputParser")
        return None, PydanticOutputParser(pydantic_object=_FallbackSummaryModel)


_REDACT_SKIP_FIELDS = frozenset({"context_dump_path", "files_modified"})


def _redact_summary_fields(summary: StructuredSummary) -> StructuredSummary:
    """Apply credential and PII redaction to all text fields of a StructuredSummary.

    Skips context_dump_path (filesystem path) and files_modified (filenames)
    which cannot contain credentials or PII. Safe no-op when nothing matches.
    """

    def _redact_text(text: str) -> str:
        result = redact_leaks(text)
        result, _ = redact_pii(result)
        return result

    for field_name in summary.__dataclass_fields__:
        if field_name in _REDACT_SKIP_FIELDS:
            continue
        value = getattr(summary, field_name)
        if isinstance(value, str) and value:
            setattr(summary, field_name, _redact_text(value))
        elif isinstance(value, list):
            setattr(
                summary,
                field_name,
                [_redact_text(item) if isinstance(item, str) else item for item in value],
            )
    return summary


def _coerce_to_structured_summary(response: object, context_dump_path: str = "") -> StructuredSummary:
    """Normalize ``with_structured_output``/parser output into a ``StructuredSummary``.

    ``with_structured_output`` returns a plain ``dict`` on JSON-mode providers
    (OpenAI-compatible), a Pydantic model on schema providers, or already a
    ``StructuredSummary`` dataclass — all three must converge before the rest
    of the pipeline reads dataclass attributes.
    """
    if isinstance(response, StructuredSummary):
        return response
    if isinstance(response, _FallbackSummaryModel):
        return response.to_structured_summary()
    if isinstance(response, dict):
        return _build_summary_from_dict(response, context_dump_path=context_dump_path)
    return parse_summary_response(response, context_dump_path=context_dump_path)


async def _invoke_summary(
    llm: BaseChatModel,
    structured_llm: object | None,
    parser: PydanticOutputParser[_FallbackSummaryModel] | None,
    prompt: str,
    dump_path: str,
    cache_prefix_messages: list[BaseMessage] | None = None,
    progress_tracker: SummaryProgressTracker | None = None,
) -> StructuredSummary:
    tracker = progress_tracker or ProgressClock()

    if parser:
        instructions = parser.get_format_instructions()
        final_prompt = f"{prompt}\n\n{instructions}"
        messages = _build_summary_invocation_messages(final_prompt, cache_prefix_messages)
        response = await _stream_with_progress(llm, messages, tracker)
        parsed = parser.invoke(response)
        summary = parsed.to_structured_summary()
    else:
        messages = _build_summary_invocation_messages(prompt, cache_prefix_messages)
        tracker.touch()
        response = await structured_llm.ainvoke(messages)  # type: ignore
        tracker.touch()
        summary = _coerce_to_structured_summary(response, dump_path)

    summary.context_dump_path = dump_path
    summary = _redact_summary_fields(summary)
    return summary


async def _stream_with_progress(
    llm: BaseChatModel,
    messages: list[BaseMessage],
    tracker: SummaryProgressTracker | ProgressClock,
) -> AIMessage:
    """Stream LLM response token-by-token, calling tracker.touch() on each chunk.

    Falls back to ainvoke if the model does not support astream or if
    astream fails (e.g. in test mocks that don't implement async iteration).
    """
    try:
        stream = llm.astream(messages)
        if not hasattr(stream, "__aiter__"):
            raise NotImplementedError("astream did not return an async iterator")
        chunks: list[str] = []
        async for chunk in stream:
            token = chunk.text if isinstance(chunk, BaseMessage) else str(chunk)
            if token:
                chunks.append(token)
                tracker.touch()
        return AIMessage(content="".join(chunks))
    except (NotImplementedError, TypeError, AttributeError):
        tracker.touch()
        response = await llm.ainvoke(messages)
        tracker.touch()
        return (
            response
            if isinstance(response, AIMessage)
            else AIMessage(content=str(getattr(response, "content", response)))
        )


def _build_summary_invocation_messages(
    prompt: str,
    cache_prefix_messages: list[BaseMessage] | None,
) -> list[BaseMessage]:
    # Aux-guard head trimming can orphan tool results; re-pair like the main call (healthy prefix stays identical).
    # The summary call runs under its own prompt, so the provider could not take signed reasoning back.
    return [*without_thinking_blocks(normalize_messages(cache_prefix_messages or [])), HumanMessage(content=prompt)]
