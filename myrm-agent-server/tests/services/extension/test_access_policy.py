"""Unit tests for extension access policy evaluation."""

from __future__ import annotations

from app.services.extension.access_policy import (
    ExtensionAccessPolicy,
    is_internal_browser_url,
    is_policy_valid_for_automation,
    is_tab_accessible,
    match_domain,
    prune_paused_tab_ids,
)


def test_empty_domain_policy_is_invalid() -> None:
    policy = ExtensionAccessPolicy(allow_all_eligible_tabs=False, authorized_domains=[])
    assert is_policy_valid_for_automation(policy) is False


def test_allow_all_policy_is_valid() -> None:
    policy = ExtensionAccessPolicy(allow_all_eligible_tabs=True, authorized_domains=[])
    assert is_policy_valid_for_automation(policy) is True


def test_domain_allowlist_requires_match() -> None:
    policy = ExtensionAccessPolicy(
        allow_all_eligible_tabs=False,
        authorized_domains=["*.x.com"],
    )
    assert is_tab_accessible(
        tab_id=1,
        url="https://x.com/home",
        domain="x.com",
        policy=policy,
    )
    assert not is_tab_accessible(
        tab_id=2,
        url="https://mail.google.com",
        domain="mail.google.com",
        policy=policy,
    )


def test_empty_domain_does_not_allow_tabs_in_relay() -> None:
    policy = ExtensionAccessPolicy(allow_all_eligible_tabs=False, authorized_domains=[])
    assert not is_tab_accessible(
        tab_id=3,
        url="https://github.com",
        domain="github.com",
        policy=policy,
    )


def test_paused_tab_is_hidden() -> None:
    policy = ExtensionAccessPolicy(
        allow_all_eligible_tabs=True,
        authorized_domains=[],
        paused_tab_ids=frozenset({42}),
    )
    assert not is_tab_accessible(
        tab_id=42,
        url="https://example.com",
        domain="example.com",
        policy=policy,
    )


def test_paused_tab_visible_when_pause_ignored() -> None:
    policy = ExtensionAccessPolicy(
        allow_all_eligible_tabs=True,
        authorized_domains=[],
        paused_tab_ids=frozenset({42}),
    )
    assert is_tab_accessible(
        tab_id=42,
        url="https://example.com",
        domain="example.com",
        policy=policy,
        respect_pause=False,
    )


def test_prune_paused_tab_ids_drops_missing_tabs() -> None:
    paused = frozenset({1, 42, 99})
    active = frozenset({1, 42})
    assert prune_paused_tab_ids(paused, active) == frozenset({1, 42})


def test_prune_paused_tab_ids_noop_when_empty() -> None:
    assert prune_paused_tab_ids(frozenset(), frozenset({1})) == frozenset()


def test_internal_urls_rejected() -> None:
    policy = ExtensionAccessPolicy(allow_all_eligible_tabs=True, authorized_domains=[])
    assert is_internal_browser_url("chrome://settings")
    assert not is_tab_accessible(
        tab_id=5,
        url="chrome://settings",
        domain="",
        policy=policy,
    )


def test_match_domain_wildcard() -> None:
    assert match_domain("sub.example.com", ["*.example.com"])
    assert match_domain("example.com", ["*.example.com"])


def test_normalize_domain_patterns_dedupes_and_strips() -> None:
    from app.services.extension.access_policy import normalize_domain_patterns

    assert normalize_domain_patterns([" Example.COM. ", "example.com", "", "  "]) == ["example.com"]


def test_match_domain_empty_domain() -> None:
    assert match_domain("", ["example.com"]) is False
    assert match_domain("   ", ["example.com"]) is False


def test_is_internal_browser_url_edge_cases() -> None:
    assert is_internal_browser_url("") is True
    assert is_internal_browser_url("about:blank") is False
    assert is_internal_browser_url("about:newtab") is False
    assert is_internal_browser_url("edge://settings") is True
    assert is_internal_browser_url("brave://settings") is True


def test_is_eligible_http_url() -> None:
    from app.services.extension.access_policy import is_eligible_http_url

    assert is_eligible_http_url("https://example.com/path") is True
    assert is_eligible_http_url("file:///tmp/a.html") is True
    assert is_eligible_http_url("ftp://example.com") is False
    assert is_eligible_http_url("") is False
    assert is_eligible_http_url("chrome://settings") is False


def test_tab_accessible_derives_domain_from_url() -> None:
    policy = ExtensionAccessPolicy(
        allow_all_eligible_tabs=False,
        authorized_domains=["github.com"],
    )
    assert is_tab_accessible(
        tab_id=7,
        url="https://github.com/octo/repo",
        domain="",
        policy=policy,
    )


def test_is_navigation_target_allowed() -> None:
    from app.services.extension.access_policy import is_navigation_target_allowed

    allow_all = ExtensionAccessPolicy(allow_all_eligible_tabs=True, authorized_domains=[])
    assert is_navigation_target_allowed("https://example.com", allow_all) is True
    assert is_navigation_target_allowed("chrome://settings", allow_all) is False
    assert is_navigation_target_allowed("ftp://example.com", allow_all) is False

    allowlist = ExtensionAccessPolicy(
        allow_all_eligible_tabs=False,
        authorized_domains=["*.x.com"],
    )
    assert is_navigation_target_allowed("https://mobile.x.com/home", allowlist) is True
    assert is_navigation_target_allowed("https://google.com", allowlist) is False

    empty = ExtensionAccessPolicy(allow_all_eligible_tabs=False, authorized_domains=[])
    assert is_navigation_target_allowed("https://example.com", empty) is False
