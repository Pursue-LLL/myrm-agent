"""Recovery Actions URL Mapper for LLM Errors.

Maps error codes to recovery actions with business-specific URLs.
Error translation is handled by Harness layer (LLMErrorDiagnostic).
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.llms.errors import FailoverReason

from app.platform_utils.deployment_capabilities import get_deployment_capabilities

# ============================================================================
# Action ID Mappings (Error Code -> Action IDs)
# ============================================================================

_ACTION_MAPPINGS: dict[FailoverReason, list[str]] = {
    FailoverReason.RATE_LIMIT: ["wait", "switch_model"],
    FailoverReason.OVERLOADED: ["wait", "switch_model"],
    FailoverReason.TIMEOUT: ["retry", "check_network"],
    FailoverReason.BILLING: ["top_up", "switch_api_key"],
    FailoverReason.AUTH_PERMANENT: ["check_api_key"],
    FailoverReason.SESSION_EXPIRED: ["re_login"],
    FailoverReason.MODEL_NOT_FOUND: ["verify_model_name"],
    FailoverReason.FORMAT_ERROR: ["contact_support"],
    FailoverReason.RESPONSE_FORMAT_ERROR: ["switch_model", "contact_support"],
    FailoverReason.CONTEXT_OVERFLOW: ["start_new_chat", "clear_history"],
    FailoverReason.UNKNOWN: ["retry", "contact_support"],
}

# ============================================================================
# Action Labels & URLs (Business Layer Responsibility)
# ============================================================================

_ACTION_TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "wait": {"label": "Wait", "url": ""},
        "switch_model": {"label": "Switch Model", "url": "/settings/models"},
        "retry": {"label": "Retry", "url": ""},
        "check_network": {"label": "Check Network", "url": ""},
        "top_up": {"label": "Top Up", "url": "/pricing"},
        "switch_api_key": {"label": "Check API Key", "url": "/settings/credentials"},
        "check_api_key": {"label": "Check API Key", "url": "/settings/credentials"},
        "re_login": {"label": "Re-login", "url": "/auth/login"},
        "verify_model_name": {"label": "Verify Model", "url": "/settings/models"},
        "contact_support": {"label": "Contact Support", "url": ""},
        "start_new_chat": {"label": "New Chat", "url": "/"},
        "clear_history": {"label": "Clear History", "url": ""},
        "check_prompt_cache": {"label": "Check Cache Status", "url": ""},
        "inspect_agent_loop": {"label": "Review Loop Logic", "url": ""},
        "review_recent_changes": {"label": "Undo Recent Changes", "url": ""},
    },
    "zh": {
        "wait": {"label": "等待", "url": ""},
        "switch_model": {"label": "切换模型", "url": "/settings/models"},
        "retry": {"label": "重试", "url": ""},
        "check_network": {"label": "检查网络", "url": ""},
        "top_up": {"label": "前往充值", "url": "/pricing"},
        "switch_api_key": {"label": "检查 API Key", "url": "/settings/credentials"},
        "check_api_key": {"label": "检查 API Key", "url": "/settings/credentials"},
        "re_login": {"label": "重新登录", "url": "/auth/login"},
        "verify_model_name": {"label": "核对模型名称", "url": "/settings/models"},
        "contact_support": {"label": "联系客服", "url": ""},
        "start_new_chat": {"label": "开启新对话", "url": "/"},
        "clear_history": {"label": "清理历史", "url": ""},
        "check_prompt_cache": {"label": "检查缓存状态", "url": ""},
        "inspect_agent_loop": {"label": "检查循环逻辑", "url": ""},
        "review_recent_changes": {"label": "撤销最近修改", "url": ""},
    },
}

# Other languages fallback to English
_ACTION_TRANSLATIONS["ja"] = _ACTION_TRANSLATIONS["en"]
_ACTION_TRANSLATIONS["ko"] = _ACTION_TRANSLATIONS["en"]
_ACTION_TRANSLATIONS["de"] = _ACTION_TRANSLATIONS["en"]

# ============================================================================
# Recovery Actions Generator
# ============================================================================


def _resolve_action_url(action_id: str, default_url: str) -> str:
    """Map recovery URLs for sandbox (platform WU) vs local (BYOK) deployments."""
    if action_id == "top_up" and get_deployment_capabilities().uses_platform_budget:
        return "/subscription"
    return default_url


def generate_recovery_actions(error_code: FailoverReason, locale: str = "en") -> list[dict[str, str]]:
    """Generate recovery actions with localized labels and business URLs.

    Args:
        error_code: The standardized error code from Harness (FailoverReason).
        locale: User's preferred language (e.g., 'en', 'zh-CN', 'ja').

    Returns:
        A list of recovery action dictionaries: [{"id": str, "label": str, "url": str}, ...]
    """
    # Get action IDs for this error code
    action_ids = _ACTION_MAPPINGS.get(error_code, [])

    # Get language-specific labels and URLs
    lang = locale[:2].lower()  # 'zh-CN' -> 'zh'
    action_dict = _ACTION_TRANSLATIONS.get(lang, _ACTION_TRANSLATIONS["en"])

    # Build structured recovery actions
    recovery_actions = []
    for action_id in action_ids:
        if action_id in action_dict:
            action_info = action_dict[action_id]
            recovery_actions.append(
                {
                    "id": action_id,
                    "label": action_info["label"],
                    "url": _resolve_action_url(action_id, action_info["url"]),
                }
            )
        else:
            # Fallback if action is missing in dictionary
            recovery_actions.append(
                {
                    "id": action_id,
                    "label": action_id.replace("_", " ").title(),
                    "url": "",
                }
            )

    return recovery_actions
