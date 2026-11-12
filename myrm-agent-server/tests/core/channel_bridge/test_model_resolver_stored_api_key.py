"""``_extract_stored_api_key`` reads only what the user typed into a provider's key list.

Callers that hand the key to one vendor's host (balance probes, xAI search) must never receive the OAuth token or
the local no-auth marker that model calls fall back to.
"""

from __future__ import annotations

from app.core.channel_bridge.model_resolver import (
    _LOCAL_NO_AUTH_API_KEY_MARKER,
    _extract_active_key,
    _extract_all_active_keys,
    _extract_stored_api_key,
)


def _entry(key: str, *, active: bool = True) -> dict[str, object]:
    """One ``apiKeys`` entry as the WebUI stores it."""
    return {"id": f"id-{key}", "key": key, "remark": "", "isActive": active}


def test_first_active_key_wins() -> None:
    provider: dict[str, object] = {
        "id": "deepseek",
        "apiKeys": [_entry("sk-off", active=False), _entry("sk-first"), _entry("sk-second")],
    }

    assert _extract_stored_api_key(provider) == "sk-first"


def test_blank_and_inactive_entries_are_skipped_and_the_key_is_trimmed() -> None:
    provider: dict[str, object] = {
        "apiKeys": [_entry("   "), _entry(""), _entry("sk-off", active=False), _entry("  sk-real  ")],
    }

    assert _extract_stored_api_key(provider) == "sk-real"


def test_no_usable_entry_gives_none() -> None:
    assert _extract_stored_api_key({}) is None
    assert _extract_stored_api_key({"apiKeys": []}) is None
    assert _extract_stored_api_key({"apiKeys": [_entry("sk-off", active=False)]}) is None
    assert _extract_stored_api_key({"apiKeys": "sk-flat"}) is None
    assert _extract_stored_api_key({"apiKeys": ["sk-flat", None, 7]}) is None


def test_flat_api_key_field_is_not_a_stored_key() -> None:
    assert _extract_stored_api_key({"id": "xai", "apiKey": "sk-flat"}) is None


def test_oauth_token_and_no_auth_marker_are_not_stored_keys() -> None:
    oauth_provider: dict[str, object] = {"id": "xai", "apiKeys": [], "_oauthToken": "oauth-token"}
    local_provider: dict[str, object] = {"id": "ollama", "apiKeys": []}

    # Model calls fall back to both of them ...
    assert _extract_active_key(oauth_provider) == "oauth-token"
    assert _extract_active_key(local_provider) == _LOCAL_NO_AUTH_API_KEY_MARKER
    # ... but neither is something the user stored.
    assert _extract_stored_api_key(oauth_provider) is None
    assert _extract_stored_api_key(local_provider) is None


def test_model_call_keys_prefer_stored_then_oauth_then_no_auth() -> None:
    stored: dict[str, object] = {"id": "ollama", "apiKeys": [_entry("sk-stored")], "_oauthToken": "oauth-token"}
    oauth: dict[str, object] = {"id": "ollama", "apiKeys": [], "_oauthToken": "oauth-token"}
    local: dict[str, object] = {"id": "ollama", "apiKeys": []}

    assert _extract_all_active_keys(stored) == ["sk-stored"]
    assert _extract_all_active_keys(oauth) == ["oauth-token"]
    assert _extract_all_active_keys(local) == [_LOCAL_NO_AUTH_API_KEY_MARKER]
