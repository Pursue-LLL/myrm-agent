"""The real claude binary receives an attached image as a base64 block on stdin, whatever its size or permission mode.

A local stub API records what the CLI sends and answers with plain text, so nothing here needs a login, a network or
a model (and no model is billed). The stub never asks the model to open a file, so an image in a request can only have
come from the image block on stdin. The sizes straddle 256 KiB, above which the CLI's own ``@`` file mention silently
drops an image, and stop below the 5 MiB the server stages at most. The turn runs through the production runtime with
the production argv and permission rules. Run with ``-m integration``; a CLI that is not installed skips its tests.
"""

from __future__ import annotations

import json
import random
import shutil
import struct
import threading
import zlib
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.auth import cli_launch_args
from myrm_agent_harness.toolkits.acp.runtime.cli.runtime import CliRuntime
from myrm_agent_harness.toolkits.acp.types import RuntimeConfig, RuntimeEventType

pytestmark = pytest.mark.integration

_CLAUDE = shutil.which("claude")

needs_claude = pytest.mark.skipif(_CLAUDE is None, reason="claude CLI not installed")


# Above this size the CLI's own ``@`` file mention drops an image without telling the model.
_MENTION_LIMIT = 256 * 1024
# What the server stages at most per image.
_STAGING_CAP = 5 * 1024 * 1024


def _write_png(path: Path, size_kib: int = 0) -> Path:
    """A valid PNG of about ``size_kib`` KiB, or a 1x1 one for 0; random pixels, stored uncompressed, keep the size."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    width = 512 if size_kib else 1
    height = size_kib * 1024 // (1 + 3 * width) if size_kib else 1
    rng = random.Random(size_kib)
    rows = b"".join(b"\x00" + rng.randbytes(3 * width) for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows, 0)) + chunk(b"IEND", b"")
    )
    return path


def _reply(text: str) -> bytes:
    """A complete streamed Anthropic message holding ``text``."""
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_stub",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-stub",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            },
        ),
        (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        ),
        (
            "content_block_delta",
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 8},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(payload)}\n\n" for name, payload in events).encode()


class _Recorder:
    """A stub Anthropic API that records the requests of the model conversation (those that carry tools)."""

    def __init__(self) -> None:
        self.conversations: list[dict[str, object]] = []
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(length) if length else b""
                if not self.path.startswith("/v1/messages"):
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.loads(raw or b"{}")
                if body.get("tools"):
                    recorder.conversations.append(body)
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                self.wfile.write(_reply("ok"))

            def do_GET(self) -> None:
                self._answer()

            def do_POST(self) -> None:
                self._answer()

            def log_message(self, format: str, *args: object) -> None:
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def blocks(self, request: int = 0) -> list[dict[str, object]]:
        """The content blocks of every message in a model request (the first by default), in order."""
        messages = self.conversations[request]["messages"]
        assert isinstance(messages, list)
        blocks: list[dict[str, object]] = []
        for message in messages:
            content = message["content"]
            blocks += [{"type": "text", "text": content}] if isinstance(content, str) else content
        return blocks

    def image_positions(self, request: int = 0) -> list[int]:
        return [i for i, block in enumerate(self.blocks(request)) if block["type"] == "image"]

    def text_position(self, needle: str, request: int = 0) -> int:
        """Where the first text block containing ``needle`` sits; the CLI adds its own text around a prompt."""
        for i, block in enumerate(self.blocks(request)):
            if block["type"] == "text" and needle in str(block["text"]):
                return i
        raise AssertionError(f"no text block contains {needle!r}")


@pytest.fixture
def stub_api() -> Iterator[_Recorder]:
    recorder = _Recorder()
    yield recorder
    recorder.close()


def _claude(tmp_path: Path, base_url: str, permission_mode: str) -> CliRuntime:
    home = tmp_path / "home"
    home.mkdir()
    config = RuntimeConfig(
        backend_type="cli",
        command=str(_CLAUDE),
        args=cli_launch_args("claude"),
        env={
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(home / ".claude"),
            "ANTHROPIC_BASE_URL": base_url,
            "ANTHROPIC_API_KEY": "sk-ant-api03-dummy",
            "API_TIMEOUT_MS": "20000",
            "DISABLE_AUTOUPDATER": "1",
            "DISABLE_TELEMETRY": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        },
        cwd=str(tmp_path),
        permission_mode=permission_mode,  # type: ignore[arg-type]
        auth_mode="api_key",
        timeout_seconds=90,
    )
    return CliRuntime("claude", config)


async def _run(runtime: CliRuntime, prompt: str, images: list[str] | None = None, session: str = "s1") -> None:
    events = [event async for event in runtime.run_turn(prompt, session, images=images)]
    assert RuntimeEventType.DONE in [event.type for event in events]


@needs_claude
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("permission_mode", "size_kib"),
    [
        pytest.param("safe", 0, id="safe-1x1"),
        pytest.param("safe", 200, id="safe-below-256KiB"),
        pytest.param("safe", 300, id="safe-above-256KiB"),
        pytest.param("safe", 4800, id="safe-near-5MiB"),
        pytest.param("ask", 300, id="ask-above-256KiB"),
        pytest.param("allow_all", 300, id="allow_all-above-256KiB"),
    ],
)
async def test_an_image_outside_the_working_directory_is_in_the_first_request_at_any_size_and_permission_mode(
    tmp_path: Path, stub_api: _Recorder, permission_mode: str, size_kib: int
) -> None:
    # The directory name is the one macOS gives application data, which has a space in it.
    image = _write_png(tmp_path.parent / f"{tmp_path.name}-state" / "Application Support" / "a1.png", size_kib)
    assert (image.stat().st_size > _MENTION_LIMIT) == (size_kib > 256)
    assert image.stat().st_size <= _STAGING_CAP

    await _run(_claude(tmp_path, stub_api.url, permission_mode), "what is in this?", [str(image)])

    assert len(stub_api.image_positions()) == 1
    assert stub_api.text_position("what is in this?") > stub_api.image_positions()[0]


@needs_claude
@pytest.mark.asyncio
async def test_two_images_arrive_as_two_blocks_in_one_message(tmp_path: Path, stub_api: _Recorder) -> None:
    big = _write_png(tmp_path / "big.png", 300)
    small = _write_png(tmp_path / "small.png")

    await _run(_claude(tmp_path, stub_api.url, "safe"), "compare", [str(big), str(small)])

    first, second = stub_api.image_positions()
    assert second == first + 1
    assert stub_api.text_position("compare") > second


@needs_claude
@pytest.mark.asyncio
async def test_an_image_on_a_resumed_turn_reaches_the_model_after_the_history(
    tmp_path: Path, stub_api: _Recorder
) -> None:
    image = _write_png(tmp_path / "later.png", 300)
    runtime = _claude(tmp_path, stub_api.url, "safe")

    await _run(runtime, "first question")
    await _run(runtime, "and this picture?", [str(image)])

    assert len(stub_api.conversations) == 2
    assert stub_api.image_positions(0) == []
    (position,) = stub_api.image_positions(1)
    assert stub_api.text_position("first question", 1) < position < stub_api.text_position("and this picture?", 1)


@needs_claude
@pytest.mark.asyncio
async def test_a_turn_without_images_sends_no_image(tmp_path: Path, stub_api: _Recorder) -> None:
    await _run(_claude(tmp_path, stub_api.url, "safe"), "hello")

    assert stub_api.image_positions() == []
