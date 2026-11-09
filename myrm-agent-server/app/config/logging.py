"""[INPUT]
- myrm_agent_harness (POS: 脱敏/JSON/trace 日志组件)
- app.core.infra.log_rate_limit::LogStormFilter (POS: 重复日志限速)

[OUTPUT]
- configure_logging: 进程级日志配置
- set_debug_mode: 运行期切换级别

[POS]
全局日志配置：脱敏、JSON/文本格式、trace_id 注入、第三方库级别，以及重复日志限速
（避免死循环写满磁盘）。
"""

import logging
import os
import sys

from myrm_agent_harness.agent.security.redact import RedactingFormatter
from myrm_agent_harness.observability.tracing import JsonFormatter, TracingLogFilter

from app.config.env import is_debug_mode
from app.core.infra.log_rate_limit import LogStormFilter

_TEXT_FORMAT = "🚀 %(name)s - %(levelname)s - [%(trace_id)s] %(message)s"


def _is_json_log_format() -> bool:
    return os.getenv("MYRM_LOG_FORMAT", "").lower() == "json"


def configure_logging() -> None:
    """配置全局日志

    设置日志格式、级别，并控制第三方库的日志输出。
    应在应用启动时调用一次。

    格式选择（``MYRM_LOG_FORMAT`` 环境变量）：
    - ``json``  → 单行 JSON（适合 Loki / ELK / 云托管部署）
    - 默认      → 文本格式 + RedactingFormatter（本地开发）

    日志级别根据 DEBUG 环境变量动态调整：
    - DEBUG=true → logging.DEBUG
    - DEBUG=false or 未设置 → logging.WARNING
    """
    root_logger = logging.getLogger()
    root_logger.handlers = []

    console_handler = logging.StreamHandler(sys.stdout)

    if _is_json_log_format():
        console_handler.setFormatter(JsonFormatter())
    else:
        console_handler.setFormatter(RedactingFormatter(_TEXT_FORMAT))

    console_handler.addFilter(TracingLogFilter())
    # Bound repeated output: a looping caller must not be able to fill the disk or bury the cause.
    console_handler.addFilter(LogStormFilter())

    log_level = logging.DEBUG if is_debug_mode() else logging.WARNING
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)

    _suppress_library_logs("httpx", logging.WARNING)
    _suppress_library_logs("transformers", logging.ERROR)

    if is_debug_mode():
        _suppress_library_logs("uvicorn.access", logging.DEBUG)
    else:
        _suppress_library_logs("uvicorn.access", logging.ERROR)
    _suppress_library_logs("uvicorn.error", logging.WARNING)

    logging.getLogger("myrm_agent_harness.toolkits.web_search.processing.search_results_processor").setLevel(logging.INFO)

    # Production-visible memory monitoring (grep-friendly [MEMORY] logs)
    logging.getLogger("myrm_agent_harness.runtime.survival.resource_monitor").setLevel(logging.INFO)

    # Production-visible background maintenance: the periodic schedulers log a start line and success
    # counts at INFO. At the default WARNING level those lines are dropped, so a scheduler that never
    # starts or a maintenance pass that stops running leaves no trace; pinning them to INFO keeps that
    # evidence in the log without a debug build.
    for _module in ("app.lifecycle.schedulers", "app.services.memory.imports.integration_sync_daemon"):
        logging.getLogger(_module).setLevel(logging.INFO)


def _suppress_library_logs(logger_name: str, level: int) -> None:
    """设置指定库的日志级别"""
    logging.getLogger(logger_name).setLevel(level)


def set_debug_mode(enabled: bool = True) -> None:
    """设置调试模式"""
    level = logging.DEBUG if enabled else logging.WARNING
    logging.getLogger().setLevel(level)


__all__ = [
    "configure_logging",
    "set_debug_mode",
]
