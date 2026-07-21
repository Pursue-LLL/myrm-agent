"""Architecture test: api/ vs services/ top-level domain vocabulary.

Keep ``API_SERVICES_ALIASES`` and domain frozensets aligned with root ``CONTRIBUTING.md``
§ API ↔ Services domain vocabulary. Prevents contributor doc drift from filesystem layout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_APP_ROOT = Path(__file__).resolve().parent.parent.parent / "app"
_API_ROOT = _APP_ROOT / "api"
_SERVICES_ROOT = _APP_ROOT / "services"

# HTTP plural / grouped route trees → business-layer singular (or renamed) folders.
API_SERVICES_ALIASES: dict[str, str] = {
    "agents": "agent",
    "chats": "chat",
    "projects": "project",
    "events": "event",
    "background_tasks": "background",
    "batch_optimization": "skill_optimization",
}

SAME_NAME_DOMAINS: frozenset[str] = frozenset(
    {
        "approvals",
        "audit",
        "browser_recording",
        "budget",
        "channels",
        "checkpoint",
        "companion",
        "config",
        "connect",
        "context",
        "extension",
        "external_agents",
        "features",
        "files",
        "integrations",
        "kanban",
        "memory",
        "message_filter",
        "migration",
        "progression",
        "risk",
        "security",
        "skill_optimization",
        "skills",
        "webui",
        "wiki",
    }
)

API_ONLY_DOMAINS: frozenset[str] = frozenset(
    {
        "api_keys",
        "browser_sessions",
        "client_logs",
        "credentials",
        "cron",
        "datasets",
        "dev_gate",
        "eval",
        "goals",
        "health",
        "internal",
        "mcp",
        "media",
        "mem0_compat",
        "notifications",
        "openai_compat",
        "remote_access",
        "runs",
        "statistics",
        "stt",
        "system",
        "tasks",
        "tts",
        "voice",
        "web_push",
        "widget_storage",
        "workspace",
    }
)

SERVICES_ONLY_DOMAINS: frozenset[str] = frozenset(
    {
        "agent",
        "artifacts",
        "auth",
        "background",
        "chat",
        "event",
        "hosting",
        "infra",
        "locked_use",
        "mascot",
        "power",
        "project",
        "repair",
        "web_fetch",
    }
)


def _top_level_dirs(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {
        path.name
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith("_") and path.name != "__pycache__"
    }


@pytest.mark.architecture
def test_api_services_same_name_domains_match_disk() -> None:
    api_domains = _top_level_dirs(_API_ROOT)
    service_domains = _top_level_dirs(_SERVICES_ROOT)

    missing_api = sorted(SAME_NAME_DOMAINS - api_domains)
    missing_services = sorted(SAME_NAME_DOMAINS - service_domains)
    assert not missing_api, f"api/ missing same-name domains: {missing_api}"
    assert not missing_services, f"services/ missing same-name domains: {missing_services}"

    extra_api = sorted((api_domains & service_domains) - SAME_NAME_DOMAINS)
    assert not extra_api, (
        "Undocumented api/services same-name domains (update SAME_NAME_DOMAINS and CONTRIBUTING.md): "
        f"{extra_api}"
    )


@pytest.mark.architecture
def test_api_top_level_domain_partition() -> None:
    api_domains = _top_level_dirs(_API_ROOT)
    expected = SAME_NAME_DOMAINS | API_ONLY_DOMAINS | frozenset(API_SERVICES_ALIASES)
    assert api_domains == expected, (
        "api/ top-level domains changed. Update SAME_NAME_DOMAINS, API_ONLY_DOMAINS, "
        "API_SERVICES_ALIASES, and CONTRIBUTING.md § API ↔ Services domain vocabulary. "
        f"extra={sorted(api_domains - expected)!r} missing={sorted(expected - api_domains)!r}"
    )


@pytest.mark.architecture
def test_services_top_level_domain_partition() -> None:
    service_domains = _top_level_dirs(_SERVICES_ROOT)
    expected = SAME_NAME_DOMAINS | SERVICES_ONLY_DOMAINS | frozenset(API_SERVICES_ALIASES.values())
    assert service_domains == expected, (
        "services/ top-level domains changed. Update SERVICES_ONLY_DOMAINS, API_SERVICES_ALIASES, "
        "and CONTRIBUTING.md § API ↔ Services domain vocabulary. "
        f"extra={sorted(service_domains - expected)!r} missing={sorted(expected - service_domains)!r}"
    )


@pytest.mark.architecture
def test_api_services_alias_pairs_exist_on_disk() -> None:
    api_domains = _top_level_dirs(_API_ROOT)
    service_domains = _top_level_dirs(_SERVICES_ROOT)

    for api_name, service_name in API_SERVICES_ALIASES.items():
        assert api_name in api_domains, f"Missing api/{api_name}/ for alias"
        assert service_name in service_domains, f"Missing services/{service_name}/ for alias {api_name!r}"


@pytest.mark.architecture
def test_api_services_alias_keys_do_not_collide_with_same_name() -> None:
    overlap = frozenset(API_SERVICES_ALIASES) & SAME_NAME_DOMAINS
    assert not overlap, f"Alias keys must not also be same-name domains: {sorted(overlap)!r}"

    value_overlap = frozenset(API_SERVICES_ALIASES.values()) & API_ONLY_DOMAINS
    assert not value_overlap, f"Alias values must not be listed as api-only: {sorted(value_overlap)!r}"
