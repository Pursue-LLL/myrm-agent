"""A dataset export carries no credential of a tool call, with or without PII redaction."""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.dataset_export.exporter import DatasetExporter
from myrm_agent_harness.agent.event_log.dataset_export.format_converter import (
    convert_trace,
    redact_trace_credentials,
)
from myrm_agent_harness.agent.event_log.dataset_export.protocols import ExportConfig, ExportFormat, QualityThresholds
from myrm_agent_harness.agent.event_log.trace_types import ExecutionTrace, ToolCallRecord, TraceOutcome
from myrm_agent_harness.agent.event_log.types import EventPayload, StructuredEvent

_COOKIE = "Zx81qPw0Lm3"
_PASSWORD = "Summer2024!"
_TOKEN = "sk-test-abcdefghijklmnopqrstuvwxyz1234567890abcdef"
_SECRETS = (_COOKIE, _PASSWORD, _TOKEN)
_ALL_FORMATS = (ExportFormat.SHAREGPT, ExportFormat.ALPACA, ExportFormat.OPENAI)


def _trace() -> ExecutionTrace:
    trace = ExecutionTrace(session_id="s1")
    trace.outcome = TraceOutcome.SUCCESS
    trace.task_input = f"Log me in to the portal, my key is {_TOKEN}"
    trace.output = f"Done. The request used Authorization: Bearer {_TOKEN}"
    trace.tool_calls = [
        ToolCallRecord(
            sequence=1,
            tool_name="http_request",
            start_time=1.0,
            input_data={
                "url": "https://portal.example.com/login",
                "max_tokens": 4096,
                "headers": {"Cookie": f"sessionid={_COOKIE}", "Accept": "text/html"},
                "env": {"DB_PASSWORD": _PASSWORD},
            },
            output_summary=f"< Set-Cookie: sessionid={_COOKIE}; Path=/ api_key={_TOKEN}",
            # Not part of any sample today; a format that starts to emit it must mask it first.
            output_data={"body": f"password={_PASSWORD}"},
        ),
        ToolCallRecord(sequence=2, tool_name="http_request", start_time=2.0, success=False, error=f"401 for {_TOKEN}"),
    ]
    return trace


def _events(session_id: str) -> list[StructuredEvent]:
    def event(sequence: int, event_type: str, **data: object) -> StructuredEvent:
        return StructuredEvent(
            sequence=sequence,
            timestamp=1700000000.0 + sequence,
            event_type=event_type,
            session_id=session_id,
            data=EventPayload(**data),
        )

    return [
        event(1, "session_start", task_input="Log me in to the portal and read the dashboard page"),
        event(
            2,
            "tool_start",
            tool_name="http_request",
            headers={"Cookie": f"sessionid={_COOKIE}"},
            env={"DB_PASSWORD": _PASSWORD},
        ),
        event(
            3, "tool_end", tool_name="http_request", output_summary=f"< Set-Cookie: sessionid={_COOKIE}", duration_ms=5
        ),
        event(4, "session_end", output="The dashboard page shows two open invoices for this account."),
    ]


class TestRedactTraceCredentials:
    @pytest.mark.parametrize("fmt", _ALL_FORMATS)
    def test_no_credential_of_a_tool_call_reaches_an_export_format(self, fmt: ExportFormat) -> None:
        trace = _trace()

        redact_trace_credentials(trace)

        sample = str(convert_trace(trace, fmt))
        assert [secret for secret in _SECRETS if secret in sample] == []

    def test_the_text_fields_of_the_trace_are_masked(self) -> None:
        trace = _trace()

        redact_trace_credentials(trace)

        assert _TOKEN not in trace.task_input
        assert _TOKEN not in trace.output
        assert trace.task_input.startswith("Log me in to the portal, my key is ")

    def test_ordinary_tool_arguments_keep_their_values(self) -> None:
        trace = _trace()

        redact_trace_credentials(trace)

        args = trace.tool_calls[0].input_data
        assert args["url"] == "https://portal.example.com/login"
        assert args["max_tokens"] == 4096
        assert isinstance(args["headers"], dict)
        assert args["headers"]["Accept"] == "text/html"
        assert _COOKIE not in args["headers"]["Cookie"]

    def test_a_tool_call_without_arguments_or_output_is_left_as_it_is(self) -> None:
        trace = ExecutionTrace(session_id="s1")
        trace.tool_calls = [ToolCallRecord(sequence=1, tool_name="noop", start_time=1.0)]

        redact_trace_credentials(trace)

        record = trace.tool_calls[0]
        assert (record.input_data, record.output_summary, record.error) == ({}, None, None)


class TestExporterCredentials:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("redact_pii", [True, False])
    async def test_an_export_masks_the_credentials_the_event_log_kept(self, tmp_path: Path, redact_pii: bool) -> None:
        backend = FileEventLogBackend(tmp_path / "logs", "s1")
        await backend.append(_events("s1"))
        config = ExportConfig(
            output_dir=tmp_path / "exports",
            formats=_ALL_FORMATS,
            quality=QualityThresholds(min_turns=1, min_content_length=10),
            redact_pii=redact_pii,
        )

        report = await DatasetExporter(backend).export(config)

        assert report.errors == []
        assert len(report.output_files) == len(_ALL_FORMATS)
        exported = "".join(Path(file).read_text(encoding="utf-8") for file in report.output_files)
        assert "http_request" in exported
        assert [secret for secret in (_COOKIE, _PASSWORD) if secret in exported] == []
