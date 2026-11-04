"""PTC IPC 服务端

通过 Unix Socket 为子进程提供 Programmatic Tool Calling 服务。
Agent-in-Sandbox 模式下，子进程通过 Unix Socket 与 Agent 主进程通信。

架构：
- Agent 主进程：每次脚本执行起一个 IPC Server（见 ``ipc_endpoint``），监听该次执行专属的 Unix Socket
- 子进程（代码执行）：通过 Socket 文件与主进程通信
- 路由：skill_name == "__builtin__" → BuiltinToolRegistry
         其他 → MCPSkillProxyService
- 调用方范围：会话、agent、工作区、只读状态由宿主在起服务端时固定（``CallerScope``），
  不从请求里取——脚本可以直接写套接字，请求里的任何字段都不可信。
- 调用上下文：每个请求设置 ``IPCCallContext`` 到 ContextVar，
  让 ``notify`` 等内置 handler 取到 session_id /
  workspace_root，而无需污染全局或显式参数透传。

[INPUT]
- (none)

[OUTPUT]
- IPCCallContext: Frozen per-call context (session_id, workspace_root, trace_id).
- get_ipc_call_context: ContextVar accessor for builtin handlers.
- CallerScope: Whom the script's calls are made for; fixed by the host when the server starts.
- IPCEndpoint: What the generated client needs to reach one server (path/port, token, marker nonce).
- MCPIPCRequest / MCPIPCResponse: Wire types.
- MCPIPCServer: Unix Socket server; routes requests to BuiltinToolRegistry or MCPSkillProxyService.

[POS]
PTC IPC backbone: wire types and the server. The caller's identity is the server's, not the request's;
``ipc_endpoint`` ties a server's lifetime to one script execution.
"""

import asyncio
import contextlib
import hmac
import json
import logging
import os
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from myrm_agent_harness.agent.skills.mcp.ipc_call_budget import (
    CallBudget,
)
from myrm_agent_harness.agent.skills.mcp.ipc_request_policy import (
    path_policy_error,
    read_only_policy_error,
    scope_gate_error,
)
from myrm_agent_harness.core.network.ipc_socket import (
    SOCKET_DIR_MODE,
    SOCKET_FILE_MODE,
)
from myrm_agent_harness.utils import os_compat

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IPCCallContext:
    """Per-call context for IPC handlers (notify/...).

    Set by the IPC server before dispatching to a builtin handler. Read via
    :func:`get_ipc_call_context`. Frozen so handlers cannot mutate it.
    """

    session_id: str | None
    workspace_root: str | None
    trace_id: str


_ipc_call_context: ContextVar[IPCCallContext | None] = ContextVar("ipc_call_context", default=None)


def get_ipc_call_context() -> IPCCallContext | None:
    """Return the current IPC call context, or None if outside an IPC dispatch."""
    return _ipc_call_context.get()


@dataclass(frozen=True, slots=True)
class CallerScope:
    """Whom a server's calls are made for, fixed by the host when the server starts.

    The script can write to the socket itself, so nothing in a request may say which session it
    belongs to, which workspace it may touch, or whether the run is read-only: every policy and
    budget decision reads these values from the server instead.
    """

    session_id: str | None = None
    agent_id: str | None = None
    """Agent identity for MCP scope-gate policy lookup; distinct from session_id."""
    workspace_root: str | None = None
    readonly_workspace: bool = False
    """True when the run holds a read-only capability handle: the server then refuses every MCP tool
    that does not declare readOnlyHint. Carried here, not read from the capability ContextVar, because
    the handler runs in the server's task, which cannot observe the calling run's handle."""


@dataclass(frozen=True, slots=True)
class IPCEndpoint:
    """How the generated in-script client reaches one IPC server and authenticates to it."""

    socket_path: str
    tcp_port: int
    """Loopback port on the non-POSIX transport, else 0."""
    auth_token: str
    trace_nonce: str
    """Authenticates in-script call markers on stdout: the host accepts only markers carrying it, so text
    returned by a tool (a web page, an API payload) cannot forge a citation or cut a real marker short."""


class MCPIPCRequest(BaseModel):
    """PTC IPC 请求；调用方范围不在其中（见 ``CallerScope``），请求里多出的字段被忽略。"""

    skill_name: str
    tool_name: str
    params: dict[str, object]
    trace_id: str = ""
    """Log correlation only; budgets are keyed by the server, which the script cannot re-key."""
    auth_token: str | None = None
    """Bearer token of this server; the server rejects requests that omit or fake it."""


class MCPIPCResponse(BaseModel):
    """MCP IPC 响应"""

    success: bool
    result: object | None = None
    error: str | None = None


class MCPIPCServer:
    """MCP IPC 服务端

    通过 Unix Socket 为沙箱环境提供 MCP 工具调用服务。
    """

    _SHUTDOWN_TIMEOUT = 5.0

    def __init__(self, socket_path: str, scope: CallerScope, budget: CallBudget) -> None:
        """初始化 IPC 服务端

        Args:
            socket_path: Unix Socket 文件路径
            scope: 这个服务端替谁调用；策略与预算都按它判定，不看请求
            budget: 工具调用预算；会话级兜底要跨脚本累计，所以由调用方共享，而不是每个服务端各一份
        """
        self.socket_path = socket_path
        self._scope = scope
        self._budget = budget
        self._execution_id = secrets.token_hex(8)
        self._server: asyncio.Server | None = None
        self._connections: set[asyncio.Task[None]] = set()
        self._running = False
        self._tcp_port: int = 0
        self.auth_token: str = secrets.token_urlsafe(32)
        self.trace_nonce: str = secrets.token_hex(16)

    async def start(self) -> None:
        """启动 IPC 服务端"""
        if self._running:
            logger.warning("MCP IPC Server already running")
            return

        if os_compat.IS_WIN:
            # Windows asyncio runs ProactorEventLoop, whose create_unix_connection raises
            # NotImplementedError, so the AF_UNIX path cannot work there. Bind loopback
            # TCP on an ephemeral port instead; the bearer token remains the boundary.
            self._server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)
            sockets = self._server.sockets
            if not sockets:
                raise RuntimeError("MCP IPC server bound no TCP socket")
            self._tcp_port = int(sockets[0].getsockname()[1])
            self._running = True
            logger.info(f"MCP IPC Server started at tcp://127.0.0.1:{self._tcp_port}")
            return

        # 私有目录（0700）：同机其他用户无法预建或连接 socket。
        # umask 在创建瞬间生效，消除 mkdir 与 chmod 之间被 co-tenant 打开目录 fd 的窗口。
        socket_dir = Path(self.socket_path).parent
        previous_umask = os.umask(0o077)
        try:
            socket_dir.mkdir(parents=True, exist_ok=True, mode=SOCKET_DIR_MODE)
        finally:
            os.umask(previous_umask)
        os.chmod(socket_dir, SOCKET_DIR_MODE)

        # 启动 Unix Socket 服务器
        self._server = await asyncio.start_unix_server(self._handle_client, path=self.socket_path)

        # 仅所有者可读写：访问控制由 token 与目录权限共同保证
        os.chmod(self.socket_path, SOCKET_FILE_MODE)

        self._running = True
        logger.info(f"MCP IPC Server started at {self.socket_path}")

    @property
    def tcp_port(self) -> int:
        """Loopback TCP port when the server runs on the non-POSIX transport, else 0."""
        return self._tcp_port

    @property
    def endpoint(self) -> IPCEndpoint:
        """What an in-script client needs to reach this server."""
        return IPCEndpoint(
            socket_path=self.socket_path,
            tcp_port=self._tcp_port,
            auth_token=self.auth_token,
            trace_nonce=self.trace_nonce,
        )

    async def stop(self) -> None:
        """停止 IPC 服务端并取消在途请求；可重复调用，也可用于只启动了一半的服务端"""
        self._running = False

        server, self._server = self._server, None
        if server is not None:
            server.close()
            # Handlers still waiting on a client would otherwise keep wait_closed() pending.
            for task in self._connections:
                task.cancel()
            await asyncio.gather(*self._connections, return_exceptions=True)
            self._connections.clear()
            try:
                await asyncio.wait_for(server.wait_closed(), timeout=self._SHUTDOWN_TIMEOUT)
            except TimeoutError:
                logger.warning(f"IPC Server wait_closed timed out after {self._SHUTDOWN_TIMEOUT}s, forcing shutdown")
            # The file exists only once the listener was bound; the TCP transport never creates one.
            with contextlib.suppress(FileNotFoundError):
                os.unlink(self.socket_path)

        logger.info("MCP IPC Server stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """处理客户端连接

        协议格式：
        - 请求：4字节长度 + JSON数据
        - 响应：4字节长度 + JSON数据
        """
        task = asyncio.current_task()
        if task is not None:
            self._connections.add(task)
        try:
            while True:
                length_bytes = await reader.readexactly(4)
                length = int.from_bytes(length_bytes, "big")

                if length <= 0 or length > 10 * 1024 * 1024:
                    logger.error(f"Invalid message length: {length}")
                    break

                data = await reader.readexactly(length)
                message = data.decode("utf-8")

                # No deadline of its own: a call is held to the limit its server is configured with, at the point
                # where it is made (the session actor, then ``call_backstop``). A fixed one here would cut every
                # server configured above it.
                response = await self._process_until_client_leaves(reader, message)
                if response is None:
                    break

                response_bytes = response.encode("utf-8")
                writer.write(len(response_bytes).to_bytes(4, "big"))
                writer.write(response_bytes)
                await writer.drain()

        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error(f"IPC client handler error: {e}")
        finally:
            if task is not None:
                self._connections.discard(task)
            writer.close()
            await writer.wait_closed()

    async def _process_until_client_leaves(self, reader: asyncio.StreamReader, message: str) -> str | None:
        """Answer one request, or abandon it, returning ``None``, once its client is gone.

        The generated client keeps one request in flight per connection and sends nothing while it waits, so a read
        that completes here is the connection closing (the script was stopped, or gave the call up) or a protocol
        violation. Either way nobody is left to receive the answer. Cancelling reaches the MCP server through the
        session actor; leaving the call running would hold the server, and the next script's calls with it, until
        the tool's own limit.
        """
        request = asyncio.ensure_future(self._process_request(message))
        client_gone = asyncio.ensure_future(reader.read(1))
        try:
            await asyncio.wait({request, client_gone}, return_when=asyncio.FIRST_COMPLETED)
            return request.result() if request.done() else None
        finally:
            request.cancel()
            client_gone.cancel()
            await asyncio.gather(request, client_gone, return_exceptions=True)

    async def _process_request(self, message: str) -> str:
        """处理 MCP 调用请求

        Args:
            message: JSON 格式的请求消息

        Returns:
            JSON 格式的响应消息
        """
        tid = "-"
        try:
            request_data = json.loads(message)
            request = MCPIPCRequest.model_validate(request_data)

            tid = request.trace_id[:8] if request.trace_id else "-"
            log_prefix = f"[IPC:{tid}]"

            if not self._authorize(request.auth_token):
                logger.warning(f"{log_prefix} Rejected unauthorized IPC request")
                return MCPIPCResponse(
                    success=False, error="Unauthorized: invalid or missing auth token"
                ).model_dump_json()

            budget_error = self._budget.consume(self._scope.session_id, self._execution_id)
            if budget_error is not None:
                logger.warning(f"{log_prefix} Call budget exhausted (session={self._scope.session_id})")
                return MCPIPCResponse(success=False, error=budget_error).model_dump_json()

            policy_error = read_only_policy_error(request, self._scope)
            if policy_error is not None:
                logger.warning(f"{log_prefix} Blocked by read-only policy: {request.skill_name}.{request.tool_name}")
                return MCPIPCResponse(success=False, error=policy_error).model_dump_json()

            path_error = path_policy_error(request, self._scope)
            if path_error is not None:
                logger.warning(
                    f"{log_prefix} Blocked by path policy: {request.skill_name}.{request.tool_name} - {path_error}"
                )
                return MCPIPCResponse(success=False, error=path_error).model_dump_json()

            scope_error = scope_gate_error(request, self._scope)
            if scope_error is not None:
                logger.warning(
                    f"{log_prefix} Blocked by agent scope gate: {request.skill_name}.{request.tool_name} - {scope_error}"
                )
                return MCPIPCResponse(success=False, error=scope_error).model_dump_json()

            logger.info(f"{log_prefix} Request: {request.skill_name}.{request.tool_name}")

            # Per-call context for builtin handlers (notify/...).
            # ContextVar is task-local, so concurrent IPC clients stay isolated.
            ctx_token = _ipc_call_context.set(
                IPCCallContext(
                    session_id=self._scope.session_id,
                    workspace_root=self._scope.workspace_root,
                    trace_id=tid,
                )
            )
            try:
                from myrm_agent_harness.agent.skills.mcp.builtin_registry import BUILTIN_SKILL_NAME

                if request.skill_name == BUILTIN_SKILL_NAME:
                    from myrm_agent_harness.agent.skills.mcp.builtin_registry import get_builtin_tool_registry

                    registry = get_builtin_tool_registry()
                    result = await registry.dispatch(request.tool_name, request.params, tid)
                else:
                    from myrm_agent_harness.agent.skills.mcp.proxy_service import get_mcp_skill_proxy_service

                    service = get_mcp_skill_proxy_service()
                    result = await service.invoke_tool(
                        request.skill_name,
                        request.tool_name,
                        request.params,
                        trace_id=tid,
                        session_id=self._scope.session_id or "-",
                    )
            finally:
                _ipc_call_context.reset(ctx_token)

            response = MCPIPCResponse(success=True, result=result)
            logger.info(f"{log_prefix} Success: {request.skill_name}.{request.tool_name}")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e!s}"
            logger.error(f"[IPC:{tid}] Failed: {error_msg}")
            response = MCPIPCResponse(success=False, error=error_msg)

        return response.model_dump_json()

    def _authorize(self, token: str | None) -> bool:
        """Constant-time bearer-token check.

        The token is minted per server process and handed to the child through its
        environment, so a local process cannot forge a ``session_id`` and inject
        events into another conversation.
        """
        if not token:
            return False
        return hmac.compare_digest(token, self.auth_token)
