"""WeChat Official Account API error hints for HITL draft publish.

[INPUT]
- (none)

[OUTPUT]
- resolve_wechat_api_locale: Normalize request locale for hint selection
- format_wechat_api_error_message: Locale-aware actionable errcode messages

[POS]
Business-layer WeChat API onboarding hints consumed by WeChatOfficialApiClient and draft API.
"""

from __future__ import annotations

_ERCODE_HINTS_ZH: dict[int, str] = {
    40164: ("服务器公网 IP 不在公众号后台白名单。请到「设置与开发 → 安全中心 → IP 白名单」添加本机公网 IP 后重试。"),
    48001: "接口未授权：该能力通常仅认证服务号可用。",
    40001: "access_token 无效或已过期：请核对 AppID/AppSecret，或稍后重试。",
    42001: "access_token 无效或已过期：请核对 AppID/AppSecret，或稍后重试。",
    45009: "接口调用频率超限：请稍后再试。",
    -1: "微信系统繁忙：请稍后再试。",
}

_ERCODE_HINTS_EN: dict[int, str] = {
    40164: (
        "Server public IP is not on the Official Account IP whitelist. "
        "Add it under Settings → Security Center → IP whitelist, then retry."
    ),
    48001: "API not authorized: this capability usually requires a verified service account.",
    40001: "Invalid or expired access_token: verify AppID/AppSecret or retry later.",
    42001: "Invalid or expired access_token: verify AppID/AppSecret or retry later.",
    45009: "WeChat API rate limit exceeded: retry later.",
    -1: "WeChat system busy: retry later.",
}


def resolve_wechat_api_locale(locale: str | None) -> str:
    if not locale:
        return "zh"
    normalized = locale.lower().strip()
    if normalized.startswith("zh"):
        return "zh"
    return "en"


def format_wechat_api_error_message(
    errcode: int,
    errmsg: object,
    *,
    path: str,
    locale: str = "zh",
) -> str:
    """Render a locale-aware, actionable WeChat API error for UI display."""
    resolved = resolve_wechat_api_locale(locale)
    hints = _ERCODE_HINTS_ZH if resolved == "zh" else _ERCODE_HINTS_EN
    hint = hints.get(errcode)
    if hint:
        return f"{hint} (errcode={errcode})"
    base = str(errmsg) if errmsg else "WeChat API error"
    return f"WeChat API error on {path}: {base} (errcode={errcode})"
