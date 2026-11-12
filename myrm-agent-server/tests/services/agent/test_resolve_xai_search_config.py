"""``resolve_xai_search_config`` finds xAI credentials in providers exactly as the WebUI stores them.

A stored row keeps its keys in ``apiKeys`` and its endpoint in ``apiUrl``; only a key the user typed counts, so an
injected OAuth token (handled by the subscription path) never shows up here.
"""

from __future__ import annotations

import pytest

from app.services.agent.platform_config import resolve_xai_search_config

_XAI_URL = "https://api.x.ai/v1"


def _key(key: str, *, active: bool = True) -> dict[str, object]:
    """One ``apiKeys`` entry as the WebUI stores it."""
    return {"id": f"id-{key}", "key": key, "remark": "", "isActive": active}


def _row(
    provider_id: str,
    *,
    keys: list[dict[str, object]] | None = None,
    api_url: str = _XAI_URL,
    **extra: object,
) -> dict[str, object]:
    """A stored provider row; ``keys=None`` gives it one active key."""
    return {
        "id": provider_id,
        "isEnabled": True,
        "apiKeys": [_key("xai-stored")] if keys is None else keys,
        "apiUrl": api_url,
        **extra,
    }


def test_stored_key_and_endpoint_of_the_xai_row() -> None:
    assert resolve_xai_search_config({"providers": [_row("xai")]}) == ("xai-stored", _XAI_URL)


def test_row_without_endpoint_gets_the_xai_default() -> None:
    assert resolve_xai_search_config({"providers": [_row("xai", api_url="")]}) == ("xai-stored", _XAI_URL)


def test_trailing_slash_of_the_endpoint_is_dropped() -> None:
    assert resolve_xai_search_config({"providers": [_row("xai", api_url="https://api.x.ai/v1/")]}) == (
        "xai-stored",
        _XAI_URL,
    )


def test_xai_prefixed_id_matches_with_a_custom_endpoint() -> None:
    row = _row("xai-main", api_url="https://relay.example/xai")

    assert resolve_xai_search_config({"providers": [row]}) == ("xai-stored", "https://relay.example/xai")


def test_x_ai_host_matches_with_a_custom_id() -> None:
    assert resolve_xai_search_config({"providers": [_row("grok-gateway")]}) == ("xai-stored", _XAI_URL)


def test_other_providers_are_ignored() -> None:
    row = _row("openai", api_url="https://api.openai.com/v1")

    assert resolve_xai_search_config({"providers": [row]}) is None


def test_first_active_key_is_used() -> None:
    row = _row("xai", keys=[_key("xai-off", active=False), _key("xai-first"), _key("xai-second")])

    assert resolve_xai_search_config({"providers": [row]}) == ("xai-first", _XAI_URL)


def test_a_later_xai_row_is_used_when_the_first_has_no_key() -> None:
    rows = [_row("xai", keys=[]), _row("xai-backup", keys=[_key("xai-backup-key")])]

    assert resolve_xai_search_config({"providers": rows}) == ("xai-backup-key", _XAI_URL)


@pytest.mark.parametrize(
    "row",
    [
        pytest.param(_row("xai", keys=[]), id="no-keys"),
        pytest.param(_row("xai", keys=[_key("xai-off", active=False)]), id="only-inactive-keys"),
        pytest.param(_row("xai", keys=[_key("   ")]), id="blank-key"),
        pytest.param(_row("xai", keys=[], apiKey="xai-flat"), id="flat-api-key-field"),
        pytest.param(_row("xai", keys=[], _oauthToken="oauth-token"), id="oauth-token-only"),
    ],
)
def test_without_a_key_the_user_typed_nothing_resolves(row: dict[str, object]) -> None:
    assert resolve_xai_search_config({"providers": [row]}) is None


@pytest.mark.parametrize(
    "providers_dict",
    [
        pytest.param(None, id="none"),
        pytest.param({}, id="empty"),
        pytest.param({"providers": "xai"}, id="providers-not-a-list"),
        pytest.param({"providers": ["xai", None, 3]}, id="rows-not-dicts"),
    ],
)
def test_malformed_providers_resolve_nothing(providers_dict: dict[str, object] | None) -> None:
    assert resolve_xai_search_config(providers_dict) is None
