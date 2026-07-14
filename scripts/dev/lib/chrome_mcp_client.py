"""Synchronous Chrome DevTools MCP mux client for formal UI E2E runners."""

from __future__ import annotations

import json
import logging
import os
import re
import select
import shutil
import subprocess
import threading
import time
import uuid
from builtins import BaseExceptionGroup, ExceptionGroup
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

_PAGE_RE = re.compile(r"^(?:Page\s+(?:idx\s+)?)?(\d+)\s*:", re.MULTILINE)
_TARGET_RE = re.compile(r"Myrm exact targetId:\s*([A-Za-z0-9-]+)")
_JSON_FENCE_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)
_CLEANUP_TIMEOUT_SEC = 5.0
_LOGGER = logging.getLogger(__name__)
_BENIGN_CLEANUP_TOKENS = (
    "No target with given id",
    "LEASE_NOT_ACTIVE",
    "Target closed",
    "detached Frame",
    "No page found",
)


def _is_benign_cleanup_error(message: str) -> bool:
    return any(token in message for token in _BENIGN_CLEANUP_TOKENS)


@dataclass(frozen=True, slots=True)
class McpPage:
    page_id: int
    target_id: str
    lease_id: str
    context_id: str | None = None


def _text_content(result: dict[str, object]) -> str:
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    blocks: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            value = item.get("text")
            if isinstance(value, str):
                blocks.append(value)
    return "\n".join(blocks)


def parse_new_page(result: dict[str, object]) -> tuple[int, str]:
    text = _text_content(result)
    page_matches = _PAGE_RE.findall(text)
    target_match = _TARGET_RE.search(text)
    if not page_matches or target_match is None:
        raise RuntimeError(
            f"MCP new_page did not return pageId + exact targetId: {text[:500]}"
        )
    return int(page_matches[-1]), target_match.group(1)


def parse_evaluate_result(result: dict[str, object]) -> object:
    text = _text_content(result)
    match = _JSON_FENCE_RE.search(text)
    candidate = match.group(1).strip() if match is not None else text.strip()
    if candidate.startswith("Script ran on page and returned:"):
        candidate = candidate.split(":", maxsplit=1)[1].strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return candidate


class ChromeMcpClient:
    """One mux context. Every page is paired with an exact Wave READ lease."""

    def __init__(self, *, request_timeout_sec: float = 60.0) -> None:
        self._request_timeout_sec = request_timeout_sec
        self._process: subprocess.Popen[str] | None = None
        self._request_id = 0
        self._request_lock = threading.Lock()
        self._stderr_lines: deque[str] = deque(maxlen=100)
        self._stderr_thread: threading.Thread | None = None
        self._pages: dict[int, McpPage] = {}
        self._agent_id = (
            os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
            or os.environ.get("MYRM_WAVE_AGENT_ID", "").strip()
            or f"pytest-mcp:{os.getpid()}:{uuid.uuid4().hex}"
        )
        self._monorepo_root = Path(__file__).resolve().parents[4]
        self._wave = self._monorepo_root / "myrm-agent/scripts/dev/wave.sh"

    def __enter__(self) -> ChromeMcpClient:
        self.start()
        return self

    def __exit__(self, _exc_type: object, exc: object, _traceback: object) -> None:
        try:
            self.close()
        except Exception as cleanup_error:
            if isinstance(exc, BaseException):
                raise BaseExceptionGroup(
                    "Chrome MCP test and cleanup both failed",
                    [exc, cleanup_error],
                ) from None
            raise

    def start(self) -> None:
        if self._process is not None:
            return
        node = shutil.which("node")
        if node is None:
            raise RuntimeError("Chrome MCP runner requires node")
        shim = self._monorepo_root / "scripts/dev/cdmcp-mux-autoconnect-shim.sh"
        if not shim.is_file():
            raise RuntimeError(f"Chrome MCP shim missing: {shim}")
        self._process = subprocess.Popen(
            ["bash", str(shim)],
            cwd=str(self._monorepo_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={
                **os.environ,
                "CDMCP_MUX_REQUEST_TIMEOUT_MS": os.environ.get(
                    "CDMCP_MUX_REQUEST_TIMEOUT_MS", "60000"
                ),
            },
        )
        assert self._process.stderr is not None
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(self._process.stderr,),
            name="chrome-mcp-stderr",
            daemon=True,
        )
        self._stderr_thread.start()
        response = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "myrm-pytest-mcp", "version": "1.0"},
            },
        )
        result = response.get("result")
        if not isinstance(result, dict) or not isinstance(
            result.get("capabilities"), dict
        ):
            self.close()
            raise RuntimeError(
                f"Chrome MCP initialize returned invalid result: {response}"
            )
        self._notify("notifications/initialized", {})

    def close(self) -> None:
        errors: list[Exception] = []
        for page in list(self._pages.values()):
            try:
                self.close_page(page)
            except Exception as exc:
                errors.append(exc)
        process = self._process
        self._process = None
        if process is not None:
            try:
                if process.stdin is not None:
                    process.stdin.close()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("Chrome MCP cleanup failed", errors)

    def new_page(
        self,
        url: str,
        *,
        timeout_ms: int = 15_000,
        isolated_context: str | None = None,
    ) -> McpPage:
        context_id = isolated_context.strip() if isolated_context is not None else None
        if isolated_context is not None and not context_id:
            raise ValueError("isolated_context must not be empty")
        lease_id = self._acquire_page_lease()
        page: McpPage | None = None
        try:
            arguments: dict[str, object] = {"url": url, "timeout": timeout_ms}
            if context_id is not None:
                arguments["isolatedContext"] = context_id
            result = self.call_tool(
                "new_page",
                arguments,
                timeout_sec=min(timeout_ms / 1000 + 5, self._request_timeout_sec),
            )
            page_id, target_id = parse_new_page(result)
            page = McpPage(
                page_id=page_id,
                target_id=target_id,
                lease_id=lease_id,
                context_id=context_id,
            )
            self._heartbeat_lease(lease_id)
            self._bind_page_lease(page)
            self._pages[page_id] = page
            return page
        except Exception as exc:
            cleanup_errors: list[str] = []
            if page is not None:
                try:
                    self.call_tool(
                        "close_page",
                        {"pageId": page.page_id},
                        timeout_sec=_CLEANUP_TIMEOUT_SEC,
                    )
                except (RuntimeError, TimeoutError) as cleanup_exc:
                    cleanup_errors.append(f"close_page: {cleanup_exc}")
            try:
                self._release_lease(lease_id, close_wave_if_idle=True)
            except (RuntimeError, TimeoutError) as cleanup_exc:
                cleanup_errors.append(f"release lease: {cleanup_exc}")
            if cleanup_errors:
                raise RuntimeError(
                    f"Chrome MCP new_page failed: {exc}; cleanup failed: "
                    + "; ".join(cleanup_errors)
                ) from exc
            raise

    def close_page(self, page: McpPage, *, ignore_errors: bool = False) -> None:
        errors: list[str] = []
        try:
            self.call_tool(
                "close_page",
                {"pageId": page.page_id},
                timeout_sec=_CLEANUP_TIMEOUT_SEC,
            )
        except (RuntimeError, TimeoutError) as exc:
            errors.append(f"close_page: {exc}")
        self._pages.pop(page.page_id, None)
        try:
            self._release_page_lease(page, unbind=not errors)
        except (RuntimeError, TimeoutError) as exc:
            errors.append(f"release lease: {exc}")
        if not errors:
            return
        message = "Chrome MCP page cleanup failed: " + "; ".join(errors)
        if ignore_errors or all(
            _is_benign_cleanup_error(part) for part in errors
        ):
            _LOGGER.warning(message)
            return
        raise RuntimeError(message)

    def evaluate(
        self, page: McpPage, expression: str, *, timeout_sec: float = 60.0
    ) -> object:
        function = f"async () => await (0, eval)({json.dumps(expression)})"
        result = self.call_tool(
            "evaluate_script",
            {"pageId": page.page_id, "function": function},
            timeout_sec=timeout_sec,
        )
        return parse_evaluate_result(result)

    def navigate(
        self,
        page: McpPage,
        url: str,
        *,
        timeout_ms: int = 15_000,
    ) -> None:
        try:
            self.call_tool(
                "navigate_page",
                {
                    "pageId": page.page_id,
                    "type": "url",
                    "url": url,
                    "timeout": timeout_ms,
                },
                timeout_sec=min(timeout_ms / 1000 + 5, self._request_timeout_sec),
            )
        except (RuntimeError, TimeoutError) as exc:
            if "timeout" not in str(exc).lower():
                raise
            probe = self.evaluate(
                page,
                "({href: location.href, bodyLength: document.body?.innerText?.length ?? 0})",
                timeout_sec=5.0,
            )
            if not isinstance(probe, dict):
                raise exc
            href = probe.get("href")
            body_length = probe.get("bodyLength")
            if href != url or not isinstance(body_length, int) or body_length <= 0:
                raise exc

    def reload(self, page: McpPage, *, timeout_ms: int = 15_000) -> None:
        self.call_tool(
            "navigate_page",
            {"pageId": page.page_id, "type": "reload", "timeout": timeout_ms},
            timeout_sec=min(timeout_ms / 1000 + 5, self._request_timeout_sec),
        )

    def press_key(self, page: McpPage, key: str) -> None:
        self.call_tool(
            "press_key",
            {"pageId": page.page_id, "key": key},
            timeout_sec=5.0,
        )

    def type_text(self, page: McpPage, text: str) -> None:
        self.call_tool(
            "type_text",
            {"pageId": page.page_id, "text": text},
            timeout_sec=5.0,
        )

    def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        timeout_sec: float | None = None,
    ) -> dict[str, object]:
        response = self._request(
            "tools/call",
            {"name": name, "arguments": arguments},
            timeout_sec=timeout_sec,
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"Chrome MCP {name} returned invalid result: {response}")
        if result.get("isError") is True:
            raise RuntimeError(f"Chrome MCP {name} failed: {_text_content(result)}")
        return result

    def _request(
        self,
        method: str,
        params: dict[str, object],
        *,
        timeout_sec: float | None = None,
    ) -> dict[str, object]:
        with self._request_lock:
            process = self._require_process()
            self._request_id += 1
            request_id = self._request_id
            self._write(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                },
            )
            timeout = (
                timeout_sec if timeout_sec is not None else self._request_timeout_sec
            )
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Chrome MCP {method} response timed out")
                response = self._read(process, remaining)
                if response.get("id") != request_id:
                    continue
                error = response.get("error")
                if isinstance(error, dict):
                    raise RuntimeError(
                        f"Chrome MCP {method} error: {error.get('message', error)}"
                    )
                return response

    def _notify(self, method: str, params: dict[str, object]) -> None:
        self._write(
            self._require_process(),
            {"jsonrpc": "2.0", "method": method, "params": params},
        )

    def _write(
        self, process: subprocess.Popen[str], payload: dict[str, object]
    ) -> None:
        if process.stdin is None:
            raise RuntimeError("Chrome MCP stdin is unavailable")
        process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        process.stdin.flush()

    def _read(
        self, process: subprocess.Popen[str], timeout_sec: float
    ) -> dict[str, object]:
        if process.stdout is None:
            raise RuntimeError("Chrome MCP stdout is unavailable")
        ready, _, _ = select.select([process.stdout], [], [], timeout_sec)
        if not ready:
            raise TimeoutError(
                f"Chrome MCP response timed out after {timeout_sec:.1f}s; "
                f"stderr={list(self._stderr_lines)[-5:]}"
            )
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(
                f"Chrome MCP transport closed; stderr={list(self._stderr_lines)[-5:]}"
            )
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Chrome MCP returned non-object payload: {payload}")
        return payload

    def _require_process(self) -> subprocess.Popen[str]:
        process = self._process
        if process is None or process.poll() is not None:
            raise RuntimeError("Chrome MCP client is not running")
        return process

    def _drain_stderr(self, stream: TextIO) -> None:
        for line in stream:
            self._stderr_lines.append(line.rstrip())

    def _wave_command(self, *args: str) -> dict[str, object]:
        result = subprocess.run(
            ["bash", str(self._wave), "--agent", self._agent_id, *args],
            cwd=str(self._monorepo_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Wave command failed: {result.stderr or result.stdout}")
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Wave command returned invalid payload: {result.stdout}"
            )
        return payload

    def _ensure_wave_open(self) -> None:
        result = subprocess.run(
            ["bash", str(self._wave), "status"],
            cwd=str(self._monorepo_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=os.environ.copy(),
        )
        if result.returncode == 0 and '"status": "open"' in result.stdout:
            return
        try:
            self._wave_command("open")
        except RuntimeError as exc:
            if "WAVE_ALREADY_OPEN" not in str(exc):
                raise

    def _acquire_page_lease(self) -> str:
        self._ensure_wave_open()
        payload = self._wave_command("lease", "acquire", "READ", "--ttl", "900")
        lease = payload.get("lease")
        lease_id = lease.get("leaseId") if isinstance(lease, dict) else None
        if not isinstance(lease_id, str) or not lease_id:
            raise RuntimeError(f"Wave acquire did not return leaseId: {payload}")
        return lease_id

    def _bind_page_lease(self, page: McpPage) -> None:
        args = [
            "lease",
            "bind-browser",
            page.lease_id,
            str(page.page_id),
            "--target-id",
            page.target_id,
        ]
        if page.context_id is not None:
            args.extend(("--context-id", page.context_id))
        self._wave_command(*args)

    def _release_page_lease(self, page: McpPage, *, unbind: bool) -> None:
        errors: list[str] = []
        if unbind:
            try:
                self._wave_command("lease", "unbind-browser", page.lease_id)
            except (RuntimeError, TimeoutError) as exc:
                errors.append(f"unbind: {exc}")
        try:
            self._release_lease(page.lease_id, close_wave_if_idle=True)
        except (RuntimeError, TimeoutError) as exc:
            errors.append(f"release: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))

    def _release_lease(self, lease_id: str, *, close_wave_if_idle: bool = False) -> None:
        if close_wave_if_idle:
            self._wave_command("lease", "release", lease_id, "--close-wave-if-idle")
        else:
            self._wave_command("lease", "release", lease_id)

    def _heartbeat_lease(self, lease_id: str) -> None:
        self._wave_command("lease", "heartbeat", lease_id, "--extend", "900")
