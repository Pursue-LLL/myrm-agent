"""事件记录器

管理单个 Turn 的事件记录：持久化到 SQLite + 实时回调推送。
仅在本地模式下启用。
"""

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.deploy_mode import is_local_mode
from app.database.models import AgentEvent, AgentTurn
from app.services.event.types import EventCallback, EventLevel, EventType


class EventRecorder:
    """事件记录器

    管理单个 Turn 的事件记录，支持：
    - 事件持久化到 SQLite
    - 实时回调推送
    - Turn 状态管理
    """

    def __init__(
        self,
        session: AsyncSession,
        turn_id: str,
        callback: EventCallback | None = None,
    ):
        self._session = session
        self._turn_id = turn_id
        self._callback = callback
        self._event_index = 0
        self._enabled = is_local_mode()

    @property
    def turn_id(self) -> str:
        return self._turn_id

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def record(
        self,
        event_type: EventType,
        payload: dict[str, object],
        level: EventLevel = EventLevel.INFO,
        tool_name: str | None = None,
        file_path: str | None = None,
        duration_ms: int | None = None,
    ) -> AgentEvent | None:
        """记录事件"""
        if not self._enabled:
            return None

        event = AgentEvent(
            id=str(uuid.uuid4()),
            turn_id=self._turn_id,
            event_type=event_type.value,
            level=level.value,
            event_index=self._event_index,
            payload=payload,
            tool_name=tool_name,
            file_path=file_path,
            duration_ms=duration_ms,
        )
        self._event_index += 1

        self._session.add(event)
        await self._session.flush()

        await self._update_turn_stats(event_type)

        if self._callback:
            self._callback(event)

        return event

    async def _update_turn_stats(self, event_type: EventType) -> None:
        """更新 Turn 统计信息"""
        stmt = update(AgentTurn).where(AgentTurn.id == self._turn_id).values(event_count=AgentTurn.event_count + 1)

        if event_type in (EventType.TOOL_CALL_START,):
            stmt = stmt.values(tool_call_count=AgentTurn.tool_call_count + 1)
        elif event_type == EventType.ERROR:
            stmt = stmt.values(error_count=AgentTurn.error_count + 1)

        await self._session.execute(stmt)

    async def record_tool_call_start(self, tool_name: str, tool_input: dict[str, object]) -> AgentEvent | None:
        """记录工具调用开始"""
        return await self.record(
            event_type=EventType.TOOL_CALL_START,
            payload={"input": tool_input},
            tool_name=tool_name,
        )

    async def record_tool_call_end(
        self,
        tool_name: str,
        tool_output: dict[str, object],
        duration_ms: int,
        success: bool = True,
    ) -> AgentEvent | None:
        """记录工具调用结束"""
        return await self.record(
            event_type=EventType.TOOL_CALL_END,
            payload={"output": tool_output, "success": success},
            level=EventLevel.INFO if success else EventLevel.ERROR,
            tool_name=tool_name,
            duration_ms=duration_ms,
        )

    async def record_command_start(self, command: str, cwd: str | None = None) -> AgentEvent | None:
        """记录命令执行开始"""
        return await self.record(
            event_type=EventType.COMMAND_START,
            payload={"command": command, "cwd": cwd},
        )

    async def record_command_output(
        self,
        stdout: str | None = None,
        stderr: str | None = None,
        stream_type: str = "stdout",
    ) -> AgentEvent | None:
        """记录命令输出（流式）"""
        return await self.record(
            event_type=EventType.COMMAND_OUTPUT,
            payload={"stdout": stdout, "stderr": stderr, "stream_type": stream_type},
        )

    async def record_command_end(self, exit_code: int, duration_ms: int) -> AgentEvent | None:
        """记录命令执行结束"""
        return await self.record(
            event_type=EventType.COMMAND_END,
            payload={"exit_code": exit_code},
            level=EventLevel.INFO if exit_code == 0 else EventLevel.WARNING,
            duration_ms=duration_ms,
        )

    async def record_file_diff(
        self,
        file_path: str,
        action: str,
        diff: str | None = None,
        old_content: str | None = None,
        new_content: str | None = None,
    ) -> AgentEvent | None:
        """记录文件变更"""
        return await self.record(
            event_type=EventType.FILE_DIFF,
            payload={
                "action": action,
                "diff": diff,
                "old_content": old_content,
                "new_content": new_content,
            },
            file_path=file_path,
        )

    async def record_artifact(
        self,
        file_path: str,
        artifact_type: str,
        metadata: dict[str, object] | None = None,
    ) -> AgentEvent | None:
        """记录产物生成"""
        return await self.record(
            event_type=EventType.ARTIFACT_CREATED,
            payload={"artifact_type": artifact_type, "metadata": metadata or {}},
            file_path=file_path,
        )

    async def record_permission_request(
        self,
        action: str,
        resource: str,
        details: dict[str, object] | None = None,
    ) -> AgentEvent | None:
        """记录权限请求"""
        return await self.record(
            event_type=EventType.PERMISSION_REQUEST,
            payload={"action": action, "resource": resource, "details": details or {}},
            level=EventLevel.WARNING,
        )

    async def record_permission_response(
        self,
        action: str,
        resource: str,
        approved: bool,
        reason: str | None = None,
    ) -> AgentEvent | None:
        """记录权限响应"""
        return await self.record(
            event_type=EventType.PERMISSION_RESPONSE,
            payload={
                "action": action,
                "resource": resource,
                "approved": approved,
                "reason": reason,
            },
        )

    async def record_thinking(self, content: str) -> AgentEvent | None:
        """记录 Agent 思考"""
        return await self.record(
            event_type=EventType.THINKING,
            payload={"content": content},
        )

    async def record_assistant_message(self, content: str) -> AgentEvent | None:
        """记录 Agent 消息"""
        return await self.record(
            event_type=EventType.ASSISTANT_MESSAGE,
            payload={"content": content},
        )

    async def record_error(
        self,
        error_type: str,
        message: str,
        traceback: str | None = None,
    ) -> AgentEvent | None:
        """记录错误"""
        return await self.record(
            event_type=EventType.ERROR,
            payload={
                "error_type": error_type,
                "message": message,
                "traceback": traceback,
            },
            level=EventLevel.ERROR,
        )
