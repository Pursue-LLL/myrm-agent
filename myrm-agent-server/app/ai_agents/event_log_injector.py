"""统一事件日志配置注入器与会话标识解析器.

[INPUT]
- GeneralAgentParams: 业务层通用 Agent 参数对象
- job_id / chat_id / session_id: 外部入口传入的各类会话或任务标识
- run_date: 可选的运行日期（缺省取当前 UTC 日期）

[OUTPUT]
- get_default_event_log_config: 读取服务端统一的 event_log_dir 与 max_line_bytes
- resolve_cron_event_log_session_id: 生成符合白名单并按日分片的定时任务会话标识 (cron:{job_id}:{date})
- resolve_voice_realtime_session_id: 生成符合白名单并按日分片的实时语音会话标识 (voice:realtime:{date})
- sanitize_channel_event_log_session_id: 净化渠道/外部会话标识，确保满足安全白名单
- inject_event_log_config: 为 GeneralAgentParams 统一装配事件日志配置与会话标识覆盖

[POS]
app.ai_agents 模块核心基础设施。为定时任务、IM 渠道、目标触发与语音入口提供单一、一致的
事件日志配置与防无限膨胀分片标识解析，防止非对话调用在可观测性统计中系统性漏计。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import re

from app.ai_agents.agent_params import GeneralAgentParams
from app.config.settings import get_settings
from app.core.utils.session_id import is_safe_session_id

# 允许的安全字符集：字母、数字、冒号、下划线、减号
_SAFE_CHARS_PATTERN = re.compile(r"[^A-Za-z0-9:_-]")


def get_default_event_log_config() -> tuple[str | None, int | None]:
    """获取当前服务配置的默认事件日志目录与行大小限制."""
    settings = get_settings()
    log_dir: str | None = getattr(settings.database, "event_log_dir", None)
    max_line_bytes: int | None = getattr(settings, "event_log_max_jsonl_line_bytes", None)
    return log_dir, max_line_bytes


def _get_utc_today_str(run_date: date | None = None) -> str:
    """获取 YYYY-MM-DD 格式的 UTC 日期字符串."""
    if run_date is not None:
        return run_date.isoformat()
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sanitize_channel_event_log_session_id(
    raw_session_id: str | None,
    default_prefix: str = "channel",
) -> str:
    """净化外部或渠道传入的会话标识，确保 100% 符合安全文件路径白名单.

    如果传入标识为空，则生成带默认前缀的安全标识；
    如果含有非法字符（如斜杠、空格、特殊符号），替换为下划线。
    """
    if not raw_session_id or not raw_session_id.strip():
        date_str = _get_utc_today_str()
        return f"{default_prefix}:unnamed:{date_str}"

    cleaned = _SAFE_CHARS_PATTERN.sub("_", raw_session_id.strip())
    if not is_safe_session_id(cleaned):
        # 兜底保障
        return f"{default_prefix}:sanitized:{_get_utc_today_str()}"
    return cleaned


def resolve_cron_event_log_session_id(
    job_id: str,
    run_date: date | None = None,
) -> str:
    """为定时任务生成按日分片的独立事件日志会话标识 (cron:{job.id}:{YYYY-MM-DD}).

    保证即使定时任务没有绑定用户网页对话，也能独立持久化事件日志；
    同时按日分片，使历史日志能够按文件修改时间正常老化过期，防止单一文件无限追加膨胀。
    """
    safe_job_id = _SAFE_CHARS_PATTERN.sub("_", (job_id or "job").strip())
    date_str = _get_utc_today_str(run_date)
    return f"cron:{safe_job_id}:{date_str}"


def resolve_voice_realtime_session_id(
    chat_id: str | None,
    run_date: date | None = None,
) -> str:
    """为实时语音入口生成按日分片的事件日志会话标识.

    防止使用硬编码的固定字面量 (如 "realtime-tool") 导致所有互不相关的语音调用
    无限追加到同一个日志文件从而永不过期。
    """
    if chat_id and chat_id != "realtime-tool" and is_safe_session_id(chat_id):
        return chat_id
    date_str = _get_utc_today_str(run_date)
    return f"voice:realtime:{date_str}"


def inject_event_log_config(
    params: GeneralAgentParams,
    *,
    session_id_override: str | None = None,
) -> GeneralAgentParams:
    """为指定的 GeneralAgentParams 统一注入事件日志目录、参数及会话标识.

    若 params 未设置 event_log_dir，则从系统配置注入；
    若传入 session_id_override，则写入 event_log_session_id。
    """
    default_dir, default_max_bytes = get_default_event_log_config()
    if params.event_log_dir is None and default_dir:
        params.event_log_dir = default_dir
    if params.event_log_max_jsonl_line_bytes is None and default_max_bytes:
        params.event_log_max_jsonl_line_bytes = default_max_bytes

    if session_id_override is not None:
        params.event_log_session_id = session_id_override

    return params


__all__ = [
    "get_default_event_log_config",
    "sanitize_channel_event_log_session_id",
    "resolve_cron_event_log_session_id",
    "resolve_voice_realtime_session_id",
    "inject_event_log_config",
]
