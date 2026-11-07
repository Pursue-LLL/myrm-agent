"""The permission engine refuses a URL no client reads as one host, and judges every other URL by the host it dials.

A URL with no canonical spelling (a backslash or percent-encoded host, an unreadable IPv4 address, an authority holding
two hosts) is denied before any list reads it, whatever the ruleset allows. Every other URL is judged under its
canonical host, so ``http://2130706433/`` meets the rules and the blocklist of ``127.0.0.1``.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.agent.security.engine import _check_url_syntax, evaluate_tool_call
from myrm_agent_harness.agent.security.types import PermissionAction, PermissionRule, SecurityConfig
from myrm_agent_harness.core.security.tool_registry import resolve_permission_type

_FETCH_TOOL = "web_fetch_tool"
_FETCH_PERMISSIONS = ("web_fetch", "net_fetch")


def _fetch_verdict(urls: object, config: SecurityConfig) -> tuple[PermissionAction, str]:
    """The verdict on a ``web_fetch_tool`` call, composed the way the approval middleware composes it."""
    return evaluate_tool_call(resolve_permission_type(_FETCH_TOOL), {"urls": urls}, config, tool_name=_FETCH_TOOL)


class TestCheckUrlSyntax:
    """_check_url_syntax() — a URL no client reads as one host is denied before any list reads its host."""

    @pytest.mark.parametrize("permission", ["browser_navigate", *_FETCH_PERMISSIONS])
    @pytest.mark.parametrize(
        ("url", "error"),
        [
            ("https://good.test\\@evil.test/", "parser-confusing"),
            ("https://good.test\t@evil.test/", "parser-confusing"),
            ("http://127%2e0%2e0%2e1/", "percent-encoding"),
            ("http://256.1.1.1/", "Invalid hostname"),
            ("http://[fe80::1%25en0]/", "Invalid hostname"),
            ("http://a@b@evil.test/", "Malformed URL"),
            ("http://good.test:80x/", "Invalid port"),
            ("http:///path", "Missing hostname"),
        ],
    )
    def test_a_url_with_no_canonical_form_is_denied(self, permission: str, url: str, error: str) -> None:
        key = "url" if permission == "browser_navigate" else "urls"
        value: object = url if permission == "browser_navigate" else [url]

        action, reason = _check_url_syntax(permission, {key: value})

        assert action == PermissionAction.DENY
        assert error in reason

    @pytest.mark.parametrize("permission", _FETCH_PERMISSIONS)
    @pytest.mark.parametrize("as_json_text", [False, True])
    def test_one_unreadable_url_denies_the_whole_fetch(self, permission: str, as_json_text: bool) -> None:
        urls = ["https://example.com", "http://a..b/", "https://python.org"]
        value: object = json.dumps(urls) if as_json_text else urls

        assert _check_url_syntax(permission, {"urls": value})[0] == PermissionAction.DENY

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/a",
            "http://2130706433:8080/",
            "HTTPS://Ｅxample.com./",
            "http://[::1]/",
            "localhost:3000",
        ],
    )
    def test_a_url_with_a_canonical_form_is_left_to_the_lists(self, url: str) -> None:
        assert _check_url_syntax("net_fetch", {"urls": [url]}) == (None, "")

    def test_a_tool_that_names_no_url_is_not_judged(self) -> None:
        assert _check_url_syntax("shell_exec", {"command": "curl http://a..b/"}) == (None, "")
        assert _check_url_syntax("net_fetch", {}) == (None, "")


class TestEvaluateToolCallCanonicalHost:
    """evaluate_tool_call judges the host a client dials, whatever the spelling of the URL."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://2130706433/",
            "http://0x7f.1:8080/",
            "http://0177.0.0.1/",
            "http://127.1/",
            "http://0xa9fea9fe/latest/meta-data/",
            "http://167772161/",
            "http://0300.0250.0.1/",
            "http://ｌｏｃａｌｈｏｓｔ。/",
        ],
    )
    def test_a_private_host_in_any_spelling_meets_the_default_navigation_rules(self, url: str) -> None:
        action, _ = evaluate_tool_call("browser_navigate", {"url": url}, SecurityConfig())

        assert action == PermissionAction.DENY

    def test_a_numeric_host_is_blocked_by_the_dotted_entry(self) -> None:
        config = SecurityConfig(network_blocklist=("93.184.216.34",))

        assert _fetch_verdict(["http://1572395042/"], config)[0] == PermissionAction.DENY
        assert _fetch_verdict(["http://1572395043/"], config)[0] != PermissionAction.DENY

    @pytest.mark.parametrize("permission", ["browser_navigate", *_FETCH_PERMISSIONS])
    def test_no_ruleset_allows_a_url_with_no_canonical_form(self, permission: str) -> None:
        """The syntax verdict comes before the rules, so an ``ALLOW *`` ruleset (local mode) cannot waive it."""
        allow_all = SecurityConfig(ruleset=(PermissionRule("*", "*", PermissionAction.ALLOW),))
        url = "http://good.test\\@169.254.169.254/"
        args: dict[str, object] = {"url": url} if permission == "browser_navigate" else {"urls": [url]}

        action, reason = evaluate_tool_call(permission, args, allow_all)

        assert action == PermissionAction.DENY
        assert reason.startswith("URL not allowed")
