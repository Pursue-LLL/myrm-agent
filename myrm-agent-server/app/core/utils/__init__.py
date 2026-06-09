"""Core Utilities

业务特有的工具函数模块
"""

from myrm_agent_harness.utils import extract_file_id_from_url

# 从框架层导入 ToolError（统一错误处理）
from myrm_agent_harness.utils.errors import ToolError

from app.core.utils.chat_utils import (
    ChatHistory,
    ChatHistoryReq,
    convert_chat_history,
)

# 从 errors.py 导出（业务层异常）
from app.core.utils.errors import (
    MyrmError,
    StandardHTTPException,
    authentication_error,
    conflict_error,
    external_service_error,
    field_validation_error,
    format_error_message,
    handle_llm_exception,
    internal_error,
    log_and_format_error,
    not_found_error,
    permission_error,
    register_exception_handlers,
    service_unavailable_error,
    timeout_error,
    unauthorized_error,
    unprocessable_error,
    validation_error,
)
from app.core.utils.files_utils import (
    read_image_as_base64,
)
from app.core.utils.response_utils import (
    ResponseUtils,
    list_response,
    paginated_response,
    success_response,
)

__all__ = [
    # 聊天工具
    "ChatHistory",
    "ChatHistoryReq",
    "convert_chat_history",
    # 文件工具
    "extract_file_id_from_url",
    "read_image_as_base64",
    # 响应工具
    "list_response",
    "paginated_response",
    "ResponseUtils",
    "success_response",
    # 错误处理
    "MyrmError",
    "register_exception_handlers",
    "ToolError",
    "StandardHTTPException",
    "validation_error",
    "field_validation_error",
    "not_found_error",
    "authentication_error",
    "unauthorized_error",
    "permission_error",
    "conflict_error",
    "unprocessable_error",
    "internal_error",
    "service_unavailable_error",
    "timeout_error",
    "external_service_error",
    "format_error_message",
    "log_and_format_error",
    "handle_llm_exception",
]
