"""事件系统类型定义"""

from collections.abc import Callable
from enum import Enum

from app.database.models import AgentEvent


class EventType(str, Enum):
    """事件类型枚举"""

    # 工具调用
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"

    # 命令执行
    COMMAND_START = "command_start"
    COMMAND_OUTPUT = "command_output"
    COMMAND_END = "command_end"

    # 文件操作
    FILE_DIFF = "file_diff"
    ARTIFACT_CREATED = "artifact_created"

    # 权限控制
    PERMISSION_REQUEST = "permission_request"
    PERMISSION_RESPONSE = "permission_response"

    # Agent 输出
    THINKING = "thinking"
    ASSISTANT_MESSAGE = "assistant_message"

    # 错误
    ERROR = "error"


class EventLevel(str, Enum):
    """事件级别"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TurnStatus(str, Enum):
    """Turn 状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


EventCallback = Callable[[AgentEvent], None]
