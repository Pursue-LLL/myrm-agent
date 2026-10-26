"""Turn parser — the NDJSON lines of one CLI turn in, RuntimeEvents and the turn's own verdict out.

Claude (``stream-json``), Codex (``item.*`` events and the legacy envelope) and plain-text CLIs share one parser.
It is stateful because four things only exist across lines: the session the CLI announces first, the final
``result`` line that says whether the turn failed, the ``error`` lines printed on the way (Codex reports every
retry of a request that way, so they say nothing about the turn until it ends without a verdict), and which
messages already went out as streamed text deltas (``--include-partial-messages`` repeats each message in full
afterwards).

[INPUT]
- toolkits.acp.runtime.cli.parser::event builders (POS: Shared event builders of the CLI runtime's output parsing)
- toolkits.acp.types::RuntimeEvent (POS: ACP runtime type definitions layer.)
- utils.text_utils::strip_ansi (POS: Text helpers) [lazy]

[OUTPUT]
- CliResult: the CLI's own verdict on a finished turn
- TurnParser: stateful per-turn parser (``feed`` a line, read ``announced`` / ``result`` / ``notice``)

[POS]
Output parsing of CliRuntime. Pure: no I/O, so every CLI output shape is testable from its text alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.toolkits.acp.runtime.cli.parser import (
    error_message,
    extract_text_from_event,
    parse_codex_item_event,
    parse_json_line,
    parse_thinking,
    parse_tool_result,
    parse_tool_use,
    parse_turn_failed,
    parse_usage,
    unwrap_codex_envelope,
)
from myrm_agent_harness.toolkits.acp.types import RuntimeEvent, RuntimeEventType, create_event


@dataclass(frozen=True, slots=True)
class CliResult:
    """The CLI's own verdict on a finished turn (Claude's final ``result`` line).

    ``assistant_error`` is the category Claude put on its last error message (``authentication_failed``,
    ``rate_limit``, ...); it is also set when the CLI has no API status to report, as when nobody is logged in.
    """

    is_error: bool
    subtype: str
    message: str
    terminal_reason: str
    api_error_status: int | None
    assistant_error: str = ""


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _parse_result(data: dict[str, object], assistant_error: str) -> CliResult:
    errors = data.get("errors")
    if isinstance(errors, list) and errors:
        message = "; ".join(str(error) for error in errors if error)
    else:
        message = _text(data.get("result"))
    status = data.get("api_error_status")
    return CliResult(
        is_error=data.get("is_error") is True,
        subtype=_text(data.get("subtype")),
        message=message,
        terminal_reason=_text(data.get("terminal_reason")),
        api_error_status=status if isinstance(status, int) and not isinstance(status, bool) else None,
        assistant_error=assistant_error,
    )


class TurnParser:
    """Parses the lines of one CLI turn; create one per process run."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        # API message ids whose text already went out as deltas, so the full message that follows is not repeated.
        self._streamed: set[str] = set()
        self._current_message: str | None = None
        self._announced: str | None = None
        self._assistant_error = ""
        self.result: CliResult | None = None
        # The text of the last ``error`` line; the cause of a failure that comes with no verdict of its own.
        self.notice = ""

    def take_announced(self) -> str | None:
        """The CLI session id announced since the last call (Claude ``system/init``, Codex ``thread.started``)."""
        announced, self._announced = self._announced, None
        return announced

    def feed(self, line: str) -> list[RuntimeEvent]:
        """Events carried by one stdout line; most lines carry none or one."""
        data = parse_json_line(line)
        if data is None:
            return self._plain_text(line)

        data = unwrap_codex_envelope(data)
        kind = data.get("type", "")
        if kind == "system":
            if data.get("subtype") == "init":
                self._announce(data.get("session_id"))
            return []
        if kind == "thread.started":
            self._announce(data.get("thread_id"))
            return []
        if kind == "stream_event":
            return self._stream_event(data)
        if kind == "assistant":
            return self._assistant(data)
        if kind == "user":
            return self._user(data)
        if kind == "result":
            return self._result(data)

        event = self._generic_event(str(kind), data)
        return [event] if event is not None else []

    def _announce(self, cli_session_id: object) -> None:
        if isinstance(cli_session_id, str) and cli_session_id:
            self._announced = cli_session_id

    def _text_event(self, text: str) -> RuntimeEvent:
        return create_event(RuntimeEventType.TEXT_DELTA, self._session_id, content=text)

    def _plain_text(self, line: str) -> list[RuntimeEvent]:
        from myrm_agent_harness.utils.text_utils import strip_ansi

        cleaned = strip_ansi(line).rstrip("\r\n")
        return [self._text_event(cleaned + "\n")] if cleaned else []

    def _stream_event(self, data: dict[str, object]) -> list[RuntimeEvent]:
        """Text deltas of a message being written (``--include-partial-messages``)."""
        event = data.get("event")
        if not isinstance(event, dict):
            return []
        kind = event.get("type")
        if kind == "message_start":
            message = event.get("message")
            message_id = message.get("id") if isinstance(message, dict) else None
            self._current_message = message_id if isinstance(message_id, str) and message_id else None
            if self._current_message is not None:
                self._streamed.discard(self._current_message)
            return []
        if kind != "content_block_delta":
            return []
        delta = event.get("delta")
        if not isinstance(delta, dict) or delta.get("type") != "text_delta":
            return []
        text = delta.get("text")
        message_id = data.get("api_message_id") or self._current_message
        if not (isinstance(text, str) and text and isinstance(message_id, str) and message_id):
            return []
        self._streamed.add(message_id)
        return [self._text_event(text)]

    def _assistant(self, data: dict[str, object]) -> list[RuntimeEvent]:
        """Text and tool calls of an assistant message, in the order of its content blocks."""
        error = data.get("error")
        if error:
            # The CLI's own error notice; the final ``result`` line reports the same failure.
            self._assistant_error = _text(error)
            return []
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else data.get("content")
        if isinstance(content, str):
            return [self._text_event(content)] if content else []
        if not isinstance(content, list):
            return []

        message_id = message.get("id") if isinstance(message, dict) else None
        already_streamed = isinstance(message_id, str) and message_id in self._streamed
        events: list[RuntimeEvent] = []
        text_parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text")
                if isinstance(text, str) and text and not already_streamed:
                    text_parts.append(text)
            elif block_type == "tool_use":
                if text_parts:
                    events.append(self._text_event("".join(text_parts)))
                    text_parts = []
                events.append(parse_tool_use(block, self._session_id))
        if text_parts:
            events.append(self._text_event("".join(text_parts)))
        return events

    def _user(self, data: dict[str, object]) -> list[RuntimeEvent]:
        """Tool results the CLI feeds back to the model."""
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            return []
        return [
            parse_tool_result(block, self._session_id)
            for block in content
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]

    def _result(self, data: dict[str, object]) -> list[RuntimeEvent]:
        self.result = _parse_result(data, self._assistant_error)
        usage = data.get("usage")
        return [parse_usage(usage, self._session_id)] if isinstance(usage, dict) else []

    def _generic_event(self, kind: str, data: dict[str, object]) -> RuntimeEvent | None:
        """The formats that carry one event per line: Codex ``item.*`` / ``turn.*``, legacy and generic events."""
        session_id = self._session_id
        if kind in ("item.started", "item.updated", "item.completed"):
            return parse_codex_item_event(data, session_id)

        if kind == "turn.completed":
            usage = data.get("usage")
            return parse_usage(usage, session_id) if isinstance(usage, dict) else None

        if kind == "turn.failed":
            return parse_turn_failed(data, session_id)

        if kind == "text":
            text = extract_text_from_event(data)
            return self._text_event(text) if text else None

        if kind == "agent_message":
            message = data.get("message")
            return self._text_event(message) if isinstance(message, str) and message else None

        if kind == "thinking":
            return parse_thinking(data, session_id)

        if kind == "tool_use":
            return parse_tool_use(data, session_id)

        if kind == "tool_result":
            return parse_tool_result(data, session_id)

        if kind in ("usage", "token_count"):
            info = data.get("info")
            return parse_usage(info if isinstance(info, dict) else data, session_id)

        if kind in ("error", "stream_error"):
            self.notice = error_message(data, "Unknown error")
        return None
