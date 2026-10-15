from __future__ import annotations

import logging

from app.core.security.privacy_settings import PrivacyAgentParams

from .models import AgentRequest, MultimodalQuery

logger = logging.getLogger(__name__)


def _requested_privacy_params(request: AgentRequest) -> PrivacyAgentParams:
    """The privacy fields a request itself carries.

    The web chat sends the whole policy while protection is on. A field the client did not send, the two actions
    included, is left out, so the persisted settings fill it in; an explicit off, or an explicit deep-scan choice, is
    kept as the client's.
    """
    params: PrivacyAgentParams = {}
    if request.privacy_enabled:
        params["privacy_enabled"] = True
        if request.privacy_s2_action is not None:
            params["privacy_s2_action"] = request.privacy_s2_action
        if request.privacy_s3_action is not None:
            params["privacy_s3_action"] = request.privacy_s3_action
        if request.privacy_custom_keywords_s2 is not None:
            params["privacy_custom_keywords_s2"] = request.privacy_custom_keywords_s2
        if request.privacy_custom_keywords_s3 is not None:
            params["privacy_custom_keywords_s3"] = request.privacy_custom_keywords_s3
        if request.privacy_custom_patterns_s2 is not None:
            params["privacy_custom_patterns_s2"] = request.privacy_custom_patterns_s2
        if request.privacy_custom_patterns_s3 is not None:
            params["privacy_custom_patterns_s3"] = request.privacy_custom_patterns_s3
        if request.privacy_sensitive_tools_s2 is not None:
            params["privacy_sensitive_tools_s2"] = request.privacy_sensitive_tools_s2
        if request.privacy_sensitive_tools_s3 is not None:
            params["privacy_sensitive_tools_s3"] = request.privacy_sensitive_tools_s3
    elif "privacy_enabled" in request.model_fields_set:
        params["privacy_enabled"] = False
    if request.privacy_deep_scan is not None:
        params["privacy_deep_scan"] = request.privacy_deep_scan
    return params


def _extract_code_execution_network(
    personal_settings_dict: dict[str, object] | None,
) -> bool | None:
    """Extract code execution network permission from personalSettings.

    Returns None when no user preference is set (use server default).
    """
    if not personal_settings_dict:
        return None
    value = personal_settings_dict.get("codeExecutionAllowNetwork")
    if isinstance(value, bool):
        return value
    return None


def _extract_text_from_query(query: MultimodalQuery) -> str:
    """Extract plain text from a multimodal query for DB storage and hygiene checks."""
    if isinstance(query, str):
        return query
    texts = []
    for part in query:
        if isinstance(part, dict) and part.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)
    return " ".join(texts)
