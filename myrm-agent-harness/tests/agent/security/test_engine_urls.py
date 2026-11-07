"""The permission engine judges every URL a network tool names, whatever the argument is called.

``web_fetch_tool`` receives its pages in ``urls`` (a list, or the JSON text of one) and ``browser_navigate_tool`` its
page in ``url``. The blocklist and the rule targets read both spellings, so a fetch is refused for a blocked host and
matches a host rule. Only a browser navigation asks about a domain outside the allowlist. A list entry is read by
``domain_match``, so ``*.host``, ``.host`` and ``host:port`` reach the verdict they mean.
"""

from __future__ import annotations

import json
import os

import pytest

from myrm_agent_harness.agent.security.engine import (
    _check_domain_blocklist,
    _check_domain_policy,
    _check_url_syntax,
    _resolve_targets,
    evaluate_tool_call,
    extract_url_domains,
    merge,
)
from myrm_agent_harness.agent.security.types import (
    DEFAULT_RULESET,
    PermissionAction,
    PermissionRule,
    SecurityConfig,
)
from myrm_agent_harness.core.security.tool_registry import resolve_permission_type

_FETCH_TOOL = "web_fetch_tool"
_FETCH_PERMISSIONS = ("web_fetch", "net_fetch")


def _fetch_verdict(urls: object, config: SecurityConfig) -> tuple[PermissionAction, str]:
    """The verdict on a ``web_fetch_tool`` call, composed the way the approval middleware composes it."""
    return evaluate_tool_call(resolve_permission_type(_FETCH_TOOL), {"urls": urls}, config, tool_name=_FETCH_TOOL)


class TestCheckDomainBlocklist:
    """_check_domain_blocklist() — deny blocked hostnames before the ruleset and before domain approval."""

    def test_blocked_navigation_denies(self) -> None:
        action, reason = _check_domain_blocklist(
            "browser_navigate", {"url": "https://facebook.com/login"}, ("facebook.com",)
        )

        assert action == PermissionAction.DENY
        assert "facebook.com" in reason

    @pytest.mark.parametrize("permission", _FETCH_PERMISSIONS)
    @pytest.mark.parametrize(
        "urls",
        [
            ["https://facebook.com/a"],
            ["https://facebook.com/a", "https://example.com"],
            ["https://example.com", "https://facebook.com/a"],
            '["https://example.com", "https://facebook.com/a"]',
            ["https://facebook.com./a"],
        ],
    )
    def test_a_fetch_is_denied_when_any_of_its_urls_is_blocked(self, permission: str, urls: object) -> None:
        action, reason = _check_domain_blocklist(permission, {"urls": urls}, ("facebook.com",))

        assert action == PermissionAction.DENY
        assert "facebook.com" in reason

    def test_a_url_with_no_canonical_form_is_left_to_the_syntax_check(self) -> None:
        """No host of such a URL is the one a client dials, so the blocklist has nothing to match."""
        args: dict[str, object] = {"url": "https://facebook.com\\.example.com/"}

        assert _check_domain_blocklist("browser_navigate", args, ("facebook.com",))[0] is None
        assert _check_url_syntax("browser_navigate", args)[0] == PermissionAction.DENY

    @pytest.mark.parametrize("stop", ["。", "．", "｡"])
    def test_a_trailing_full_stop_of_any_kind_does_not_leave_the_blocklist(self, stop: str) -> None:
        by_url = _check_domain_blocklist("net_fetch", {"urls": [f"https://facebook.com{stop}/x"]}, ("facebook.com",))
        by_entry = _check_domain_blocklist("net_fetch", {"urls": ["https://facebook.com/x"]}, (f"facebook.com{stop}",))

        assert by_url[0] == PermissionAction.DENY
        assert by_entry[0] == PermissionAction.DENY

    @pytest.mark.parametrize(
        ("entry", "url"),
        [
            ("xn--strae-oqa.example", "https://straße.example/x"),
            ("straße.example", "https://xn--strae-oqa.example/x"),
            ("xn--mxa9ab.example", "https://ΣΑΣ.example/x"),
            ("ΣΑΣ.example", "https://xn--mxa9ab.example/x"),
            ("127.0.0.1", "http://2130706433/x"),
            ("127.0.0.1", "http://0x7f.1:8080/x"),
            ("2130706433", "http://127.0.0.1/x"),
        ],
    )
    def test_an_entry_and_a_url_name_one_host_in_either_spelling(self, entry: str, url: str) -> None:
        assert _check_domain_blocklist("net_fetch", {"urls": [url]}, (entry,))[0] == PermissionAction.DENY

    def test_a_final_sigma_host_is_not_the_host_its_capitals_name(self) -> None:
        """``str.lower()`` reads ``ΣΑΣ`` as ``σας``; a client dials ``σασ``, and only that host is blocked."""
        urls: dict[str, object] = {"urls": ["https://ΣΑΣ.example/"]}

        assert _check_domain_blocklist("net_fetch", urls, ("σας.example",))[0] is None
        assert _check_domain_blocklist("net_fetch", urls, ("σασ.example",))[0] == PermissionAction.DENY

    @pytest.mark.parametrize("entry", ["*.evil.net", ".evil.net", ".EVIL.net:8443", "https://*.evil.net/x"])
    def test_a_wildcard_entry_blocks_the_domain_and_its_subdomains_in_every_spelling(self, entry: str) -> None:
        for url in ("https://evil.net", "https://a.b.evil.net/x"):
            assert _check_domain_blocklist("net_fetch", {"urls": [url]}, (entry,))[0] == PermissionAction.DENY
        assert _check_domain_blocklist("net_fetch", {"urls": ["https://notevil.net"]}, (entry,))[0] is None

    @pytest.mark.parametrize("entry", ["Evil.NET", "evil.net:8443", "https://evil.net/x", "evil.net."])
    def test_a_plain_entry_blocks_that_host_however_it_is_written(self, entry: str) -> None:
        assert _check_domain_blocklist("net_fetch", {"urls": ["https://evil.net/a"]}, (entry,))[0] == (
            PermissionAction.DENY
        )
        assert _check_domain_blocklist("net_fetch", {"urls": ["https://a.evil.net/a"]}, (entry,))[0] is None

    @pytest.mark.parametrize("entry", ["*", "*.*", "a.*.net"])
    def test_an_entry_naming_no_host_blocks_nothing(self, entry: str) -> None:
        assert _check_domain_blocklist("net_fetch", {"urls": ["https://evil.net"]}, (entry,))[0] is None

    def test_non_blocked_passes(self) -> None:
        assert (
            _check_domain_blocklist("web_fetch", {"urls": ["https://example.com/page"]}, ("facebook.com",))[0] is None
        )

    def test_empty_blocklist_passes(self) -> None:
        assert _check_domain_blocklist("web_fetch", {"urls": ["https://evil.com"]}, ())[0] is None

    @pytest.mark.parametrize("args", [{}, {"urls": []}, {"urls": [""]}, {"url": ""}, {"urls": "[]"}])
    def test_a_call_naming_no_url_passes(self, args: dict[str, object]) -> None:
        assert _check_domain_blocklist("net_fetch", args, ("evil.com",))[0] is None

    def test_non_url_permission_ignored(self) -> None:
        assert _check_domain_blocklist("shell_exec", {"command": "curl evil.com"}, ("evil.com",))[0] is None

    @pytest.mark.parametrize("url", ["://bad", "http://[::1"])
    def test_an_unparseable_url_passes_without_an_error(self, url: str) -> None:
        assert _check_domain_blocklist("net_fetch", {"urls": [url]}, ("evil.com",))[0] is None


class TestEvaluateToolCallBlocklist:
    """evaluate_tool_call applies network_blocklist before the rules, for every tool that names a URL."""

    _CONFIG = SecurityConfig(network_blocklist=("facebook.com", ".evil.net"))

    def test_blocked_browser_navigate_denies(self) -> None:
        action, reason = evaluate_tool_call("browser_navigate", {"url": "https://facebook.com/login"}, self._CONFIG)

        assert action == PermissionAction.DENY
        assert "facebook.com" in reason

    @pytest.mark.parametrize(
        "urls",
        [
            ["https://facebook.com/login"],
            ["https://example.com", "https://x.evil.net/p", "https://python.org"],
            json.dumps(["https://example.com", "https://facebook.com/login"]),
            ["https://facebook.com./login"],
            ["https://facebook.com。/login"],
            ["FACEBOOK.com/login"],
        ],
    )
    def test_blocked_host_in_the_urls_of_a_fetch_denies(self, urls: object) -> None:
        action, reason = _fetch_verdict(urls, self._CONFIG)

        assert action == PermissionAction.DENY
        assert "blocked by policy" in reason

    def test_deny_names_the_blocked_host(self) -> None:
        _, reason = _fetch_verdict(["https://example.com", "https://x.evil.net/p"], self._CONFIG)

        assert "x.evil.net" in reason

    def test_fetch_of_other_hosts_is_not_denied(self) -> None:
        action, _ = _fetch_verdict(["https://example.com", "https://notevil.net"], self._CONFIG)

        assert action != PermissionAction.DENY

    def test_an_entry_as_the_settings_ui_accepts_it_denies_a_fetch(self) -> None:
        """The settings form accepts ``*.host`` and ``host:port``; a list the form saved must not be inert."""
        config = SecurityConfig(network_blocklist=("*.evil.org", "bad.example:8443"))

        assert _fetch_verdict(["https://cdn.evil.org/x"], config)[0] == PermissionAction.DENY
        assert _fetch_verdict(["https://bad.example/x"], config)[0] == PermissionAction.DENY


class TestCheckDomainPolicy:
    """_check_domain_policy() — Layer 2c: a browser navigation to a domain outside the allowlist asks."""

    def test_navigation_outside_the_allowlist_asks(self) -> None:
        action, reason = _check_domain_policy("browser_navigate", {"url": "https://unknown.com"}, ("example.com",))

        assert action == PermissionAction.ASK
        assert "unknown.com" in reason

    def test_navigation_inside_the_allowlist_passes(self) -> None:
        assert (
            _check_domain_policy("browser_navigate", {"url": "https://example.com/page"}, ("example.com",))[0] is None
        )

    @pytest.mark.parametrize("entry", [".google.com", "*.google.com", "https://*.google.com/"])
    def test_a_wildcard_entry_allows_the_domain_and_its_subdomains(self, entry: str) -> None:
        for url in ("https://google.com", "https://api.google.com/v1"):
            assert _check_domain_policy("browser_navigate", {"url": url}, (entry,))[0] is None
        assert _check_domain_policy("browser_navigate", {"url": "https://notgoogle.com"}, (entry,))[0] == (
            PermissionAction.ASK
        )

    def test_a_plain_entry_allows_that_host_only(self) -> None:
        assert (
            _check_domain_policy("browser_navigate", {"url": "https://Example.COM:8443/x"}, ("example.com",))[0] is None
        )
        assert _check_domain_policy("browser_navigate", {"url": "https://a.example.com"}, ("example.com",))[0] == (
            PermissionAction.ASK
        )

    def test_trailing_dot_does_not_leave_the_allowlist(self) -> None:
        assert _check_domain_policy("browser_navigate", {"url": "https://example.com./"}, ("example.com",))[0] is None

    @pytest.mark.parametrize("args", [{}, {"url": ""}])
    def test_a_navigation_naming_no_url_passes(self, args: dict[str, object]) -> None:
        assert _check_domain_policy("browser_navigate", args, ("example.com",))[0] is None

    def test_non_url_permission_ignored(self) -> None:
        action, _ = _check_domain_policy("shell_exec", {"command": "curl https://evil.com"}, ("example.com",))

        assert action is None

    @pytest.mark.parametrize("permission", _FETCH_PERMISSIONS)
    def test_a_fetch_is_never_asked_about_its_domain(self, permission: str) -> None:
        assert _check_domain_policy(permission, {"urls": ["https://evil.com/page"]}, ("example.com",))[0] is None


class TestEvaluateToolCallDomainHitl:
    """evaluate_tool_call() with domain_hitl_enabled."""

    _CONFIG = SecurityConfig(domain_hitl_enabled=True, network_allowlist=("example.com",))

    def test_unknown_navigation_asks(self) -> None:
        action, reason = evaluate_tool_call("browser_navigate", {"url": "https://evil.com/x"}, self._CONFIG)

        assert action == PermissionAction.ASK
        assert "evil.com" in reason

    def test_known_navigation_runs_without_a_card(self) -> None:
        action, _ = evaluate_tool_call("browser_navigate", {"url": "https://example.com/x"}, self._CONFIG)

        assert action == PermissionAction.ALLOW

    def test_a_wildcard_entry_as_the_settings_ui_accepts_it_covers_the_subdomains(self) -> None:
        config = SecurityConfig(domain_hitl_enabled=True, network_allowlist=("*.example.com",))

        action, _ = evaluate_tool_call("browser_navigate", {"url": "https://api.example.com/x"}, config)

        assert action == PermissionAction.ALLOW

    def test_a_backslash_url_is_denied_and_never_asked_about(self) -> None:
        url = "http://attacker.test\\@example.com/x"

        action, reason = evaluate_tool_call("browser_navigate", {"url": url}, self._CONFIG)

        assert action == PermissionAction.DENY
        assert "parser-confusing" in reason

    def test_a_sharp_s_lookalike_of_an_allowed_host_asks(self) -> None:
        config = SecurityConfig(domain_hitl_enabled=True, network_allowlist=("wordpress.com",))

        action, reason = evaluate_tool_call("browser_navigate", {"url": "https://wordpreß.com/x"}, config)

        assert action == PermissionAction.ASK
        assert "xn--wordpre-6va.com" in reason

    def test_disabled_no_check(self) -> None:
        config = SecurityConfig(domain_hitl_enabled=False, network_allowlist=("example.com",))

        action, _ = evaluate_tool_call("browser_navigate", {"url": "https://evil.com/x"}, config)

        assert action == PermissionAction.ALLOW

    def test_non_url_tool_unaffected(self) -> None:
        config = SecurityConfig(domain_hitl_enabled=True, network_allowlist=())

        action, _ = evaluate_tool_call("file_read", {"path": "."}, config, workspace_root=os.getcwd())

        assert action == PermissionAction.ALLOW

    def test_a_fetch_of_an_unlisted_domain_is_not_held_to_the_allowlist(self) -> None:
        action, reason = _fetch_verdict(["https://evil.com/x"], self._CONFIG)

        assert action == PermissionAction.ALLOW
        assert "evil.com" not in reason


class TestExtractUrlDomains:
    """extract_url_domains() — the domains of a navigation, which the person can approve one by one."""

    def test_navigation_extracts_hostname(self) -> None:
        assert extract_url_domains("browser_navigate", {"url": "https://example.com/path"}) == ("example.com",)

    def test_hostname_is_lowercase_without_trailing_dot(self) -> None:
        assert extract_url_domains("browser_navigate", {"url": "https://Mail.Example.com./x"}) == ("mail.example.com",)

    def test_the_card_names_the_host_a_client_dials(self) -> None:
        assert extract_url_domains("browser_navigate", {"url": "http://2130706433:3000/api"}) == ("127.0.0.1",)
        assert extract_url_domains("browser_navigate", {"url": "https://Straße.de/"}) == ("xn--strae-oqa.de",)

    def test_ip_address(self) -> None:
        assert extract_url_domains("browser_navigate", {"url": "http://192.168.1.1/api"}) == ("192.168.1.1",)

    def test_non_url_permission_returns_empty(self) -> None:
        assert extract_url_domains("shell_exec", {"command": "ls"}) == ()

    @pytest.mark.parametrize("args", [{}, {"url": ""}])
    def test_a_navigation_naming_no_url_returns_empty(self, args: dict[str, object]) -> None:
        assert extract_url_domains("browser_navigate", args) == ()

    @pytest.mark.parametrize("permission", _FETCH_PERMISSIONS)
    def test_a_fetch_has_no_domain_to_approve(self, permission: str) -> None:
        assert extract_url_domains(permission, {"urls": ["https://example.com/v1"]}) == ()


class TestResolveTargets:
    """_resolve_targets() — the hosts a network tool names are what host rules such as ``*.example.com`` match."""

    def test_navigation_target_is_its_host(self) -> None:
        assert _resolve_targets("browser_navigate", {"url": "http://192.168.1.1/admin"}) == ("192.168.1.1",)

    def test_a_navigation_naming_no_url_targets_everything(self) -> None:
        assert _resolve_targets("browser_navigate", {}) == ("*",)

    @pytest.mark.parametrize("permission", _FETCH_PERMISSIONS)
    def test_a_fetch_targets_every_host_of_its_urls(self, permission: str) -> None:
        urls = ["https://api.example.com/v1", "http://localhost:3000", "https://api.example.com/v2"]

        assert _resolve_targets(permission, {"urls": urls}) == ("api.example.com", "localhost")

    def test_a_fetch_naming_no_url_targets_everything(self) -> None:
        assert _resolve_targets("net_fetch", {}) == ("*",)


class TestRulesJudgeEveryHost:
    _CONFIG = SecurityConfig(
        ruleset=merge(DEFAULT_RULESET, (PermissionRule("net_fetch", "*.internal.corp", PermissionAction.DENY),))
    )

    def test_a_host_rule_applies_to_a_fetch(self) -> None:
        assert _fetch_verdict(["https://wiki.internal.corp/page"], self._CONFIG)[0] == PermissionAction.DENY

    def test_one_matching_host_among_others_decides(self) -> None:
        urls = ["https://example.com", "https://wiki.internal.corp/x", "https://python.org"]

        assert _fetch_verdict(urls, self._CONFIG)[0] == PermissionAction.DENY
        assert _fetch_verdict(json.dumps(urls), self._CONFIG)[0] == PermissionAction.DENY

    def test_other_hosts_are_not_affected(self) -> None:
        assert _fetch_verdict(["https://example.com", "https://internal.corp.example.org"], self._CONFIG)[0] != (
            PermissionAction.DENY
        )
