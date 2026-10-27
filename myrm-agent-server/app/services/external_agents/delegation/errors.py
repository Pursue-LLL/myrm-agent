"""直连委托的失败指引：外部 Agent 几类用户可以自己处置的失败，翻译成带处置步骤的错误事件。

[INPUT]
- myrm_agent_harness.api::AgentEventType (POS: 前端 SSE 事件类型)
- myrm_agent_harness.toolkits.acp.types::AcpError, AcpErrorCode (POS: 外部 Agent 委托协议：运行时事件、错误码、委托池)

[OUTPUT]
- delegate_error_event: 未登录 / API Key 被拒 / 未安装 / 超时 → 带 diagnostic_result 与 recovery_actions 的错误事件（API Key 被拒时点名该 Agent 读取的环境变量）；其余失败返回 None
- agent_unavailable_event: 用户指定的外部 Agent 不在可用后端中 → 同形状的错误事件
- delegate_denied_event: 安全策略不允许委托给外部 Agent → 指向「设置 → 安全策略」的错误事件
- delegate_failed_event: 直连委托在到达 CLI 的结果之前就出了意外 → 同形状的错误事件

[POS]
外部 Agent 直连路径的失败文案层（Server 业务层，中英两套；ja/ko/de 回退英文，与 llm_errors 一致）。事件形状沿用
前端 ErrorStreamEvent 契约（`diagnostic_result.resolution_steps` 必须是数组），步骤文案只说用户要做什么，
不带异常名、路径或命令行；唯一点名的是 API Key 模式下该 Agent 读取的环境变量名（设置页「环境变量」里用户自己填的就是它）。其余失败（限流、进程崩溃、CLI 自己报告的错误）保持 CLI 的原话，不在这里改写。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

from myrm_agent_harness.api import AgentEventType
from myrm_agent_harness.toolkits.acp.types import AcpError, AcpErrorCode

_Kind: TypeAlias = Literal["auth_subscription", "auth_api_key", "not_installed", "timeout", "unavailable", "denied", "failed"]

# 外部 Agent 的登录 / 安装 / API Key 都在「设置 → 开发者 → 外部 Agent」；是否允许委托在「设置 → 安全策略」。
_DEVELOPER_SETTINGS: Final = "/settings/developer"
_SECURITY_SETTINGS: Final = "/settings/security"


@dataclass(frozen=True, slots=True)
class _Action:
    """The button under the error that opens the settings page where the user fixes it."""

    id: str
    label: str
    url: str


@dataclass(frozen=True, slots=True)
class _Guidance:
    message: str
    steps: tuple[str, ...]
    action: _Action | None
    # Used instead of ``steps`` when the environment variables the agent reads its key from are known (``{names}``).
    steps_naming_env: tuple[str, ...] | None = None


_GUIDANCE: Final[dict[str, dict[_Kind, _Guidance]]] = {
    "en": {
        "auth_subscription": _Guidance(
            "{agent} isn't signed in, or its sign-in has expired.",
            ("Open Settings → Developer → External Agents and sign in to {agent}.", "Then send your message again."),
            _Action("open_external_agents", "Open Settings", _DEVELOPER_SETTINGS),
        ),
        "auth_api_key": _Guidance(
            "The API key for {agent} was rejected.",
            ("Check the API key under Settings → Developer → External Agents.", "Then send your message again."),
            _Action("open_external_agents", "Open Settings", _DEVELOPER_SETTINGS),
            (
                "Check {names} under Settings → Developer → External Agents → Environment variables.",
                "Then send your message again.",
            ),
        ),
        "not_installed": _Guidance(
            "{agent} isn't installed on this computer.",
            ("Install {agent} under Settings → Developer → External Agents.", "Then send your message again."),
            _Action("install_external_agent", "Install in Settings", _DEVELOPER_SETTINGS),
        ),
        "timeout": _Guidance(
            "{agent} took too long and was stopped.",
            ("Split the task into smaller steps and send it again.",),
            None,
        ),
        "unavailable": _Guidance(
            "{agent} isn't available right now.",
            ("Check that {agent} is installed and enabled under Settings → Developer → External Agents.",),
            _Action("open_external_agents", "Open Settings", _DEVELOPER_SETTINGS),
        ),
        "denied": _Guidance(
            "Your security policy doesn't allow sending this to {agent}.",
            (
                "Open Settings → Security Policy and allow the “External CLI agent” permission.",
                "Then send your message again.",
            ),
            _Action("open_security_settings", "Open Settings", _SECURITY_SETTINGS),
        ),
        "failed": _Guidance(
            "{agent} stopped unexpectedly.",
            (
                "Send your message again.",
                "If it keeps happening, check that {agent} still works under Settings → Developer → External Agents.",
            ),
            _Action("open_external_agents", "Open Settings", _DEVELOPER_SETTINGS),
        ),
    },
    "zh": {
        "auth_subscription": _Guidance(
            "{agent} 尚未登录，或登录已过期。",
            ("前往「设置 → 开发者 → 外部 Agent」登录 {agent}。", "登录后重新发送消息。"),
            _Action("open_external_agents", "打开设置", _DEVELOPER_SETTINGS),
        ),
        "auth_api_key": _Guidance(
            "{agent} 的 API Key 被拒绝。",
            ("在「设置 → 开发者 → 外部 Agent」中检查 API Key。", "修改后重新发送消息。"),
            _Action("open_external_agents", "打开设置", _DEVELOPER_SETTINGS),
            ("在「设置 → 开发者 → 外部 Agent → 环境变量」中检查 {names}。", "修改后重新发送消息。"),
        ),
        "not_installed": _Guidance(
            "这台电脑上没有安装 {agent}。",
            ("在「设置 → 开发者 → 外部 Agent」中安装 {agent}。", "安装后重新发送消息。"),
            _Action("install_external_agent", "前往安装", _DEVELOPER_SETTINGS),
        ),
        "timeout": _Guidance(
            "{agent} 运行时间过长，已被停止。",
            ("把任务拆成更小的步骤后重新发送。",),
            None,
        ),
        "unavailable": _Guidance(
            "{agent} 当前不可用。",
            ("在「设置 → 开发者 → 外部 Agent」中确认 {agent} 已安装并启用。",),
            _Action("open_external_agents", "打开设置", _DEVELOPER_SETTINGS),
        ),
        "denied": _Guidance(
            "安全策略不允许把这条消息交给 {agent} 处理。",
            ("前往「设置 → 安全策略」，允许「外部 CLI 智能体」权限。", "修改后重新发送消息。"),
            _Action("open_security_settings", "打开设置", _SECURITY_SETTINGS),
        ),
        "failed": _Guidance(
            "{agent} 意外停止了。",
            ("请重新发送消息。", "如果反复出现，请在「设置 → 开发者 → 外部 Agent」中确认 {agent} 仍可正常使用。"),
            _Action("open_external_agents", "打开设置", _DEVELOPER_SETTINGS),
        ),
    },
}


def _language(locale: str) -> str:
    return "zh" if locale[:2].lower() == "zh" else "en"


def _kind_of(error: AcpError, auth_mode: str) -> _Kind | None:
    match error.code:
        case AcpErrorCode.AUTH_FAILED:
            return "auth_api_key" if auth_mode == "api_key" else "auth_subscription"
        case AcpErrorCode.BACKEND_NOT_FOUND:
            return "not_installed"
        case AcpErrorCode.TIMEOUT:
            return "timeout"
        case _:
            return None


def _guidance_event(kind: _Kind, agent: str, locale: str, api_key_env: tuple[str, ...] = ()) -> dict[str, object]:
    language = _language(locale)
    guidance = _GUIDANCE[language][kind]
    message = guidance.message.format(agent=agent)
    steps = guidance.steps_naming_env if api_key_env and guidance.steps_naming_env else guidance.steps
    names = " / ".join(api_key_env)
    event: dict[str, object] = {
        "type": AgentEventType.ERROR.value,
        "data": message,
        "diagnostic_result": {
            "error_type": f"external_agent_{kind}",
            "user_message": message,
            "resolution_steps": [step.format(agent=agent, names=names) for step in steps],
            "locale": language,
        },
    }
    if guidance.action is not None:
        action = guidance.action
        event["recovery_actions"] = [{"id": action.id, "label": action.label, "url": action.url}]
    return event


def delegate_error_event(
    agent: str, error: AcpError, *, auth_mode: str, locale: str, api_key_env: tuple[str, ...] = ()
) -> dict[str, object] | None:
    """The error event telling the user what to do about ``error``, or None when the CLI's own words say it best.

    ``api_key_env`` are the environment variables ``agent`` reads its API key from; a rejected key names them.
    """
    kind = _kind_of(error, auth_mode)
    return _guidance_event(kind, agent, locale, api_key_env) if kind is not None else None


def agent_unavailable_event(agent: str, locale: str) -> dict[str, object]:
    """The error event for a forced external agent that is not among the available backends."""
    return _guidance_event("unavailable", agent, locale)


def delegate_denied_event(agent: str, locale: str) -> dict[str, object]:
    """The error event for a forced external agent the security policy does not let the user delegate to."""
    return _guidance_event("denied", agent, locale)


def delegate_failed_event(agent: str, locale: str) -> dict[str, object]:
    """The error event for a forced delegation that broke before the CLI produced an answer or an error of its own."""
    return _guidance_event("failed", agent, locale)
