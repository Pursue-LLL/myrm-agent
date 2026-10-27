"""The real claude binary attaches an image named as a quoted ``@`` mention in the prompt, on the turn's first request.

A local stub API records what the CLI sends and answers with plain text, so nothing here needs a login, a network or
a model (and no model is billed). The point of the ``@"<path>"`` mention is that the image does not depend on the model
choosing to open a path with a tool; the stub never asks for one, so an image in the first request can only have come
from the mention. The turn runs through the production runtime with the production argv and permission rules.
Run with ``-m integration``; a CLI that is not installed skips its tests.
"""

from __future__ import annotations

import json
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


def _write_png(path: Path) -> Path:
    """A valid 1x1 red PNG, so the CLI has an image it can decode."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixel = zlib.compress(b"\x00" + bytes([255, 0, 0, 255]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixel) + chunk(b"IEND", b""))
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

    def block_kinds(self) -> list[str]:
        """The content-block kinds of every message in the first model request."""
        messages = self.conversations[0]["messages"]
        assert isinstance(messages, list)
        kinds: list[str] = []
        for message in messages:
            content = message["content"]
            kinds += ["text"] if isinstance(content, str) else [block["type"] for block in content]
        return kinds


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


@needs_claude
@pytest.mark.asyncio
@pytest.mark.parametrize("permission_mode", ["safe", "ask", "allow_all"])
async def test_an_image_outside_the_working_directory_is_in_the_first_request_in_every_permission_mode(
    tmp_path: Path, stub_api: _Recorder, permission_mode: str
) -> None:
    # The directory name is the one macOS gives application data: a space, which only the quotes carry through.
    image = _write_png(tmp_path.parent / f"{tmp_path.name}-state" / "Application Support" / "a1.png")
    runtime = _claude(tmp_path, stub_api.url, permission_mode)

    events = [event async for event in runtime.run_turn("what is in this?", "s1", images=[str(image)])]

    assert RuntimeEventType.DONE in [event.type for event in events]
    assert "image" in stub_api.block_kinds()


@needs_claude
@pytest.mark.asyncio
async def test_a_turn_without_images_sends_no_image(tmp_path: Path, stub_api: _Recorder) -> None:
    runtime = _claude(tmp_path, stub_api.url, "safe")

    events = [event async for event in runtime.run_turn("hello", "s1")]

    assert RuntimeEventType.DONE in [event.type for event in events]
    assert "image" not in stub_api.block_kinds()
