"""Live command output is scrubbed on whole lines, so a secret split across reads never reaches the UI.

``scrub_sensitive_info`` only recognises a credential or key block that arrives in one piece, while a shell hands
its output over in arbitrary reads. The processor therefore scrubs the accumulated text after buffering and emits
whole lines only. Every test below feeds the processor with the throttle already expired, which is the worst case:
each read would be emitted at once if it were allowed to.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.models import scrub_sensitive_info
from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession, SessionConfig
from myrm_agent_harness.toolkits.code_execution.session.stream_output_processor import (
    _SSE_HOLD_MAX_CHARS,
    StreamOutputProcessor,
)

_KEY = "sk-ant-api03-Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv1Wx2Yz3"
_KEY_BODY = "Kl6Mn7Op8Qr9St0Uv"
_PEM_BODY = "MIIEowIBAAKCAQEAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
_PEM = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    f"{_PEM_BODY}\n"
    "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy\n"
    "-----END RSA PRIVATE KEY-----\n"
)


def _ready() -> StreamOutputProcessor:
    sop = StreamOutputProcessor()
    sop._last_sse_time = time.monotonic() - 1.0
    return sop


def _feed(sop: StreamOutputProcessor, chunk: str) -> str | None:
    """One read arriving after the throttle window has passed."""
    sop._last_sse_time = time.monotonic() - 1.0
    return sop.accumulate_sse(chunk)


def _stream(chunks: list[str]) -> str:
    """Everything the UI would receive for these reads, including the final flush."""
    sop = _ready()
    emitted = [_feed(sop, chunk) or "" for chunk in chunks]
    return "".join(emitted) + sop.flush()


class TestSplitSecrets:
    """The text the UI receives equals the scrub of the whole output, wherever the reads were cut."""

    @pytest.mark.parametrize("cut", range(1, len(f"export TOKEN={_KEY} done\n")))
    def test_api_key_split_at_every_position(self, cut: int) -> None:
        text = f"export TOKEN={_KEY} done\n"
        shown = _stream([text[:cut], text[cut:]])

        assert shown == scrub_sensitive_info(text)
        assert _KEY_BODY not in shown

    @pytest.mark.parametrize("cut", range(1, len(_PEM)))
    def test_private_key_block_split_at_every_position(self, cut: int) -> None:
        shown = _stream([_PEM[:cut], _PEM[cut:]])

        assert shown == scrub_sensitive_info(_PEM)
        assert _PEM_BODY not in shown

    def test_secret_split_across_many_small_reads(self) -> None:
        text = f"before\ntoken {_KEY} end\nafter\n"
        shown = _stream(list(text))

        assert shown == scrub_sensitive_info(text)

    def test_home_path_split_across_reads_is_scrubbed(self) -> None:
        text = "see /Users/alice/project/file.txt now\n"
        shown = _stream([text[:12], text[12:]])

        assert shown == scrub_sensitive_info(text)
        assert "alice" not in shown


class TestWholeLineEmission:
    def test_unfinished_line_waits_for_its_newline(self) -> None:
        sop = _ready()

        assert _feed(sop, "partial ") is None
        assert _feed(sop, "line\n") == "partial line\n"

    def test_only_the_complete_lines_are_emitted(self) -> None:
        sop = _ready()

        assert _feed(sop, "one\ntwo\nthr") == "one\ntwo\n"
        assert sop.flush() == "thr"

    def test_flush_scrubs_the_unfinished_tail(self) -> None:
        sop = _ready()

        assert _feed(sop, f"token {_KEY}") is None
        assert sop.flush() == scrub_sensitive_info(f"token {_KEY}")
        assert _KEY_BODY not in scrub_sensitive_info(f"token {_KEY}")

    def test_carriage_return_progress_is_not_withheld(self) -> None:
        sop = _ready()

        assert _feed(sop, "downloading 50%\r") == "downloading 50%\r"

    def test_waiting_does_not_use_up_the_throttle_window(self) -> None:
        """Nothing was emitted while waiting, so the line that completes goes out on the very next read."""
        sop = _ready()

        assert sop.accumulate_sse("half ") is None
        assert sop.accumulate_sse("done\n") == "half done\n"


class TestOpenKeyBlock:
    def test_block_without_its_end_line_is_held(self) -> None:
        sop = _ready()
        head = f"-----BEGIN RSA PRIVATE KEY-----\n{_PEM_BODY}\n"

        assert _feed(sop, "before\n" + head) == "before\n"
        assert _feed(sop, _PEM.split(_PEM_BODY + "\n")[1]) == scrub_sensitive_info(_PEM)

    def test_the_whole_begin_line_is_held_with_its_prefix(self) -> None:
        sop = _ready()

        assert _feed(sop, 'private_key = "-----BEGIN PRIVATE KEY-----\nAAAA\n') is None

    def test_text_after_a_closed_block_is_not_held(self) -> None:
        sop = _ready()

        assert _feed(sop, _PEM + "next\n") == scrub_sensitive_info(_PEM + "next\n")

    def test_only_the_open_block_is_held_when_an_earlier_one_closed(self) -> None:
        sop = _ready()

        shown = _feed(sop, _PEM + f"-----BEGIN RSA PRIVATE KEY-----\n{_PEM_BODY}\n")

        assert shown == scrub_sensitive_info(_PEM)
        assert _PEM_BODY not in (shown or "")


class TestHoldCap:
    def test_an_endless_line_is_released(self) -> None:
        sop = _ready()
        released = _feed(sop, "x" * (_SSE_HOLD_MAX_CHARS + 10))

        assert released is not None
        assert len(released) == _SSE_HOLD_MAX_CHARS + 10
        assert sop.flush() == ""

    def test_an_open_key_block_is_released_at_the_cap(self) -> None:
        sop = _ready()
        released = _feed(sop, "-----BEGIN PRIVATE KEY-----\n" + ("A" * 80 + "\n") * (_SSE_HOLD_MAX_CHARS // 80 + 1))

        assert released
        assert sop.flush() == ""


class TestTeeStaysRaw:
    @pytest.mark.asyncio
    async def test_tee_keeps_the_secret_while_the_ui_does_not(self) -> None:
        sop = _ready()
        sop.setup_tee("/tmp")
        tee = AsyncMock()
        text = f"token {_KEY} end\n"

        await sop.write_tee(tee, text)
        shown = sop.accumulate_sse(text)

        tee.write.assert_called_once_with(text)
        assert shown is not None
        assert _KEY_BODY not in shown


def _config() -> SessionConfig:
    return SessionConfig(session_id="stream-scrub", work_dir="/tmp", timeout=15, sandbox_mode="disable")


# The shell pauses between the halves, so they reach the processor in separate reads and separate throttle windows.
_SPLIT_KEY_COMMAND = f"printf 'token {_KEY[:24]}'; sleep 0.4; printf '{_KEY[24:]} end\\n'"


class TestRealShell:
    @pytest.mark.asyncio
    async def test_execute_path_does_not_show_a_split_key(self) -> None:
        session = LocalPersistentSession(_config())
        await session.start()
        chunks: list[str] = []

        async def capture(event_type: str, data: dict[str, str]) -> None:
            if event_type == "tool_stdout_chunk":
                chunks.append(data["chunk"])

        try:
            with patch("myrm_agent_harness.utils.event_utils.dispatch_custom_event", side_effect=capture):
                result = await session.execute(_SPLIT_KEY_COMMAND)
            assert result.success, result.error
        finally:
            await session.close()

        shown = "".join(chunks)
        assert _KEY_BODY not in shown
        assert "sk-ant" in shown
        assert "end" in shown

    @pytest.mark.asyncio
    async def test_stream_path_does_not_show_a_split_key(self) -> None:
        session = LocalPersistentSession(_config())
        await session.start()
        try:
            shown = "".join([chunk async for chunk in session.execute_stream(_SPLIT_KEY_COMMAND)])
        finally:
            await session.close()

        assert _KEY_BODY not in shown
        assert "sk-ant" in shown
        assert "end" in shown
