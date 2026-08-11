"""Tests for the readiness MCP dimension scoped-secret preflight.

Covers ``_check_mcp``'s secret check: bound MCP servers that declare
``requiredSecrets`` or ``{{secret:KEY}}`` header references must have matching
keys in the agent vault, otherwise a WARNING item deep-links to the agent
settings page so missing credentials surface before runtime instead of failing
silently at connection time.

Also covers org-managed MCP servers (pushed by the Control Plane): they are
treated as configured even when absent from the user's own MCP config, matching
the runtime merge via config_parsers.merge_org_mcp_configs. Also covers the shared
``merge_org_mcp_configs`` helper used by every execution entry point.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.agent.profile.profile_resolver import ResolvedAgentProfile


def _profile(mcp_ids: tuple[str, ...] = ("github-monitor",)) -> ResolvedAgentProfile:
    return ResolvedAgentProfile(
        agent_id="agent-1",
        skill_ids=(),
        mcp_ids=mcp_ids,
        enabled_builtin_tools=("web_fetch",),
    )


def _mcp_dict(servers: list[dict[str, object]]) -> dict[str, object]:
    return {"mcpConfigs": servers}


def _org_mcp_dict(servers: list[dict[str, object]]) -> dict[str, object]:
    return {"servers": servers}


@pytest.fixture
def _vault(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    store = AsyncMock()
    store.list_secret_keys = AsyncMock(return_value=["GITHUB_TOKEN", "REGION"])
    monkeypatch.setattr(
        "app.services.agent.backends.secret_backend.DatabaseSecretBackend",
        lambda: store,
    )
    return store


@pytest.mark.asyncio
async def test_full_secrets_no_warning(_vault: AsyncMock) -> None:
    from app.services.agent.readiness.resolver import _check_mcp

    mcp_dict = _mcp_dict(
        [
            {
                "name": "github-monitor",
                "type": "sse",
                "url": "https://example.com/mcp",
                "enabled": True,
                "requiredSecrets": ["GITHUB_TOKEN", "REGION"],
            }
        ]
    )
    assert await _check_mcp(_profile(), mcp_dict) == []


@pytest.mark.asyncio
async def test_missing_required_secret_warns(_vault: AsyncMock) -> None:
    from app.services.agent.readiness.resolver import _check_mcp

    mcp_dict = _mcp_dict(
        [
            {
                "name": "github-monitor",
                "type": "sse",
                "url": "https://example.com/mcp",
                "enabled": True,
                "requiredSecrets": ["GITHUB_TOKEN", "MISSING_TOKEN"],
            }
        ]
    )
    items = await _check_mcp(_profile(), mcp_dict)
    assert len(items) == 1
    item = items[0]
    assert item.dimension == "mcp"
    assert item.level.value == "warning"
    assert "MISSING_TOKEN" in item.reason
    assert item.settings_path == "/settings/agents?agentId=agent-1#secrets"


@pytest.mark.asyncio
async def test_header_secret_reference_warns(_vault: AsyncMock) -> None:
    from app.services.agent.readiness.resolver import _check_mcp

    mcp_dict = _mcp_dict(
        [
            {
                "name": "slack-mcp",
                "type": "sse",
                "url": "https://example.com/mcp",
                "enabled": True,
                "headers": {"Authorization": "Bearer {{secret:SLACK_TOKEN}}"},
            }
        ]
    )
    items = await _check_mcp(_profile(mcp_ids=("slack-mcp",)), mcp_dict)
    assert len(items) == 1
    assert "SLACK_TOKEN" in items[0].reason


@pytest.mark.asyncio
async def test_disabled_server_skipped_in_secret_check(_vault: AsyncMock) -> None:
    from app.services.agent.readiness.resolver import _check_mcp

    mcp_dict = _mcp_dict(
        [
            {
                "name": "enabled-mcp",
                "type": "sse",
                "url": "https://example.com/enabled",
                "enabled": True,
                "requiredSecrets": ["GITHUB_TOKEN"],
            },
            {
                "name": "disabled-mcp",
                "type": "sse",
                "url": "https://example.com/disabled",
                "enabled": False,
                "requiredSecrets": ["ONLY_DISABLED_NEEDS"],
            },
        ]
    )
    items = await _check_mcp(
        _profile(mcp_ids=("enabled-mcp", "disabled-mcp")), mcp_dict
    )
    reasons = " ".join(item.reason for item in items)
    assert "ONLY_DISABLED_NEEDS" not in reasons


@pytest.mark.asyncio
async def test_no_required_secrets_no_warning() -> None:
    from app.services.agent.readiness.resolver import _check_mcp

    mcp_dict = _mcp_dict(
        [
            {
                "name": "plain-mcp",
                "type": "stdio",
                "command": "echo",
                "enabled": True,
            }
        ]
    )
    assert await _check_mcp(_profile(mcp_ids=("plain-mcp",)), mcp_dict) == []


@pytest.mark.asyncio
async def test_vault_error_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    store = AsyncMock()
    store.list_secret_keys = AsyncMock(side_effect=RuntimeError("vault unavailable"))
    monkeypatch.setattr(
        "app.services.agent.backends.secret_backend.DatabaseSecretBackend",
        lambda: store,
    )

    from app.services.agent.readiness.resolver import _check_mcp

    mcp_dict = _mcp_dict(
        [
            {
                "name": "github-monitor",
                "type": "sse",
                "url": "https://example.com/mcp",
                "enabled": True,
                "requiredSecrets": ["GITHUB_TOKEN"],
            }
        ]
    )
    assert await _check_mcp(_profile(), mcp_dict) == []


@pytest.mark.asyncio
async def test_org_mcp_bound_no_missing_warning(_vault: AsyncMock) -> None:
    """Agent bound to an org-managed MCP must not report 'not found in config'.

    Org MCPs are merged into runtime config via config_parsers.merge_org_mcp_configs
    regardless of user config, so readiness must treat them as configured.
    """
    from app.services.agent.readiness.resolver import _check_mcp

    org_mcp_dict = _org_mcp_dict(
        [
            {
                "name": "org-crm",
                "type": "sse",
                "url": "https://crm.example.com/mcp",
            }
        ]
    )
    assert await _check_mcp(
        _profile(mcp_ids=("org-crm",)), None, org_mcp_dict
    ) == []


@pytest.mark.asyncio
async def test_org_mcp_missing_secret_warns(_vault: AsyncMock) -> None:
    """Org MCP missing required secret surfaces a WARNING with secrets deep-link."""
    from app.services.agent.readiness.resolver import _check_mcp

    org_mcp_dict = _org_mcp_dict(
        [
            {
                "name": "org-crm",
                "type": "sse",
                "url": "https://crm.example.com/mcp",
                "requiredSecrets": ["ORG_CRM_TOKEN", "MISSING_ORG_KEY"],
            }
        ]
    )
    items = await _check_mcp(
        _profile(mcp_ids=("org-crm",)), None, org_mcp_dict
    )
    assert len(items) == 1
    item = items[0]
    assert item.dimension == "mcp"
    assert item.level.value == "warning"
    assert "MISSING_ORG_KEY" in item.reason
    assert item.settings_path == "/settings/agents?agentId=agent-1#secrets"


def test_extract_org_mcp_configs_tags_scope_and_skips_invalid() -> None:
    """Org MCP parsing matches converter.py: scope=org tag, no enabled filter."""
    from app.core.channel_bridge.config_parsers import extract_org_mcp_configs

    org_mcp_dict = _org_mcp_dict(
        [
            {
                "name": "org-crm",
                "type": "sse",
                "url": "https://crm.example.com/mcp",
                "enabled": False,
            },
            {"name": "broken"},
        ]
    )
    parsed = extract_org_mcp_configs(org_mcp_dict)
    assert len(parsed) == 1
    assert parsed[0].name == "org-crm"
    assert parsed[0].extra_params == {"scope": "org"}
    assert extract_org_mcp_configs(None) == []
    assert extract_org_mcp_configs({"servers": "not-a-list"}) == []


def test_merge_org_mcp_configs_appends_org_servers() -> None:
    """User configs come first, then org servers tagged scope=org."""
    from app.core.channel_bridge.config_parsers import (
        extract_mcp_configs,
        merge_org_mcp_configs,
    )

    user = extract_mcp_configs(
        _mcp_dict(
            [
                {
                    "name": "user-db",
                    "type": "sse",
                    "url": "https://user.example.com/mcp",
                    "enabled": True,
                }
            ]
        )
    )
    org_mcp_dict = _org_mcp_dict(
        [
            {
                "name": "org-crm",
                "type": "sse",
                "url": "https://crm.example.com/mcp",
            }
        ]
    )
    merged = merge_org_mcp_configs(user, org_mcp_dict)
    assert [c.name for c in merged] == ["user-db", "org-crm"]
    assert merged[1].extra_params == {"scope": "org"}
    assert merged[0].extra_params is None


def test_merge_org_mcp_configs_org_only() -> None:
    """Org servers are available even when the user has no MCP config of their own."""
    from app.core.channel_bridge.config_parsers import merge_org_mcp_configs

    org_mcp_dict = _org_mcp_dict(
        [
            {
                "name": "org-wiki",
                "type": "sse",
                "url": "https://wiki.example.com/mcp",
            }
        ]
    )
    merged = merge_org_mcp_configs(None, org_mcp_dict)
    assert [c.name for c in merged] == ["org-wiki"]
    assert merged[0].extra_params == {"scope": "org"}


def test_merge_org_mcp_configs_none_inputs() -> None:
    """Both inputs empty yields an empty list (no crash, fresh list)."""
    from app.core.channel_bridge.config_parsers import merge_org_mcp_configs

    assert merge_org_mcp_configs(None, None) == []
    assert merge_org_mcp_configs([], None) == []
    assert merge_org_mcp_configs(None, {"servers": "not-a-list"}) == []


def test_merge_org_mcp_configs_does_not_mutate_input() -> None:
    """The user list is copied; callers can reuse their original reference."""
    from app.core.channel_bridge.config_parsers import (
        extract_mcp_configs,
        merge_org_mcp_configs,
    )

    user = extract_mcp_configs(
        _mcp_dict(
            [
                {
                    "name": "user-db",
                    "type": "sse",
                    "url": "https://user.example.com/mcp",
                    "enabled": True,
                }
            ]
        )
    )
    org_mcp_dict = _org_mcp_dict(
        [
            {
                "name": "org-crm",
                "type": "sse",
                "url": "https://crm.example.com/mcp",
            }
        ]
    )
    before = len(user)
    merge_org_mcp_configs(user, org_mcp_dict)
    assert len(user) == before
