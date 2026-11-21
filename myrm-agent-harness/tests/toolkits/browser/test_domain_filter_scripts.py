"""Page scripts the domain filter registers: the CSP meta builder (Layer 0) and the hardening script (Layer 2)."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist
from myrm_agent_harness.toolkits.browser.domain_filter.scripts import build_csp_meta_script, build_init_script

# =============================================================================
# build_csp_meta_script - Layer 0
# =============================================================================


def test_build_csp_meta_script_structure() -> None:
    """Test CSP meta script generates valid structure."""
    allowlist = DomainAllowlist(patterns=("example.com",))

    script = build_csp_meta_script(allowlist)

    assert script.startswith("(function() {")
    assert "createElementNS(xhtml, 'meta')" in script
    assert "Content-Security-Policy" in script
    assert "connect-src" in script
    assert script.strip().endswith("})();")


def test_build_csp_meta_script_waits_for_the_head_the_parser_builds_instead_of_creating_one() -> None:
    """An init script runs before the parser has made a head: creating one ahead of it would give the page two."""
    script = build_csp_meta_script(DomainAllowlist(patterns=("example.com",)))
    at_load = script[script.index("if (document.head)") : script.index("['WebSocket'")]

    assert "MutationObserver" in at_load
    assert "DOMContentLoaded" in at_load
    assert "createElement" not in at_load


def test_build_csp_meta_script_gives_a_document_with_no_head_one_in_the_xhtml_namespace() -> None:
    """An SVG or XML document has no head and an element it creates by name is not an HTML one; it is made on demand."""
    script = build_csp_meta_script(DomainAllowlist(patterns=("example.com",)))
    head_of = script[script.index("function headOf(doc)") : script.index("function ensurePolicy()")]

    assert "createElementNS(xhtml, 'head')" in head_of
    assert "if (!doc.head) created.remove();" in head_of


def test_build_csp_meta_script_includes_domains() -> None:
    """Test CSP script includes allowed domains without protocol prefix."""
    allowlist = DomainAllowlist(patterns=("example.com", "*.github.com"))

    script = build_csp_meta_script(allowlist)

    assert "example.com" in script
    assert "github.com" in script


def test_build_csp_meta_script_directives() -> None:
    """Test CSP includes required directives."""
    allowlist = DomainAllowlist(patterns=("example.com",))

    script = build_csp_meta_script(allowlist)

    assert "connect-src" in script
    assert "script-src" in script
    assert "frame-src" in script
    assert "object-src 'none'" in script
    assert "default-src" not in script


def test_build_csp_meta_script_rejects_an_empty_allowlist() -> None:
    """An empty allowlist is no filter at all, so there is no policy to build; ``install_domain_filter`` never asks."""
    with pytest.raises(ValueError, match="empty"):
        build_csp_meta_script(DomainAllowlist(patterns=()))


def test_build_csp_meta_script_applies_the_policy_before_the_channels_no_request_filter_sees() -> None:
    """A reused popup window keeps the script's globals but not its document, so the constructors apply the policy."""
    script = build_csp_meta_script(DomainAllowlist(patterns=("example.com",)))

    for channel in ("WebSocket", "Worker", "SharedWorker"):
        assert f"'{channel}'" in script
    assert "new Proxy(" in script
    assert "Reflect.construct" in script
    assert script.count("connect-src 'self' example.com") == 1


def test_build_csp_meta_script_adds_no_second_policy_to_a_document_that_already_carries_it() -> None:
    """The page's world and the agent's world each run this script with a record of their own: the document decides."""
    script = build_csp_meta_script(DomainAllowlist(patterns=("example.com",)))
    ensure = script[script.index("function ensurePolicy()") : script.index("if (document.head)")]

    assert ensure.index("if (!carries(doc))") < ensure.index("createElementNS(xhtml, 'meta')")


def test_build_csp_meta_script_evaluates_to_a_check_of_the_current_document() -> None:
    """The agent's world runs the script as an expression and asks it whether the document carries the policy."""
    script = build_csp_meta_script(DomainAllowlist(patterns=("example.com",)))
    returned = script[script.rindex("return function()") :]

    assert "ensurePolicy();" in returned
    assert "return carries(document);" in returned


def test_build_csp_meta_script_wildcard_domain_expansion() -> None:
    """Test wildcard domain generates both bare and wildcard entries."""
    allowlist = DomainAllowlist(patterns=("*.github.com",))

    script = build_csp_meta_script(allowlist)

    assert "github.com" in script
    assert "*.github.com" in script


def test_build_csp_meta_script_mixed_domains() -> None:
    """Test mix of exact and wildcard domains."""
    allowlist = DomainAllowlist(patterns=("example.com", "*.github.com"))

    script = build_csp_meta_script(allowlist)

    assert "example.com" in script
    assert "github.com" in script
    assert "*.github.com" in script


def test_build_csp_meta_script_no_default_src() -> None:
    """Test CSP does not include default-src to allow CDN resources."""
    allowlist = DomainAllowlist(patterns=("example.com",))

    script = build_csp_meta_script(allowlist)

    assert "default-src" not in script


def test_build_csp_meta_script_special_characters_in_domain() -> None:
    """Test CSP script handles special characters in domains."""
    allowlist = DomainAllowlist(patterns=("example-site.co.uk",))
    script = build_csp_meta_script(allowlist)

    assert "example-site.co.uk" in script


def test_build_csp_meta_script_many_patterns() -> None:
    """Test CSP script with many patterns."""
    patterns = tuple(f"domain{i}.com" for i in range(50))
    allowlist = DomainAllowlist(patterns=patterns)

    script = build_csp_meta_script(allowlist)

    assert "domain0.com" in script
    assert "domain49.com" in script


# =============================================================================
# build_init_script - Layer 2
# =============================================================================


def test_build_init_script_structure() -> None:
    """Test build_init_script generates valid JavaScript."""
    script = build_init_script()

    assert script.startswith("(function() {")
    assert "_harden" in script
    assert script.strip().endswith("})();")


def test_build_init_script_rtc_patching() -> None:
    """Test script includes RTCPeerConnection patching."""
    script = build_init_script()

    assert "RTCPeerConnection" in script
    assert "SecurityError" in script
    assert "blocked by domain policy" in script


def test_build_init_script_webtransport_patching() -> None:
    """Test script includes WebTransport patching."""
    script = build_init_script()

    assert "WebTransport" in script
    assert "SecurityError" in script


def test_build_init_script_service_worker_disabled() -> None:
    """Test script disables Service Worker registration."""
    script = build_init_script()

    assert "serviceWorker" in script
    assert "register" in script
    assert "Promise.reject" in script


def test_build_init_script_object_define_property() -> None:
    """Test script uses Object.defineProperty for hardening."""
    script = build_init_script()

    assert "Object.defineProperty" in script
    assert "writable: false" in script
    assert "configurable: false" in script


def test_build_init_script_leaves_a_property_that_is_already_locked_down() -> None:
    """A window the init script hardened is hardened again when the agent's script arms it: that must change nothing."""
    script = build_init_script()
    harden = script[script.index("function _harden(") : script.index("if (typeof RTCPeerConnection")]

    assert harden.index("getOwnPropertyDescriptor") < harden.index("Object.defineProperty")
    assert "return;" in harden[: harden.index("Object.defineProperty")]


def test_build_init_script_no_domain_logic() -> None:
    """Test script does not include domain checking (delegated to CSP)."""
    script = build_init_script()

    assert "_isAllowed" not in script
    assert "_checkUrl" not in script
    assert "_patterns" not in script
    assert "WebSocket" not in script
    assert "EventSource" not in script
    assert "sendBeacon" not in script
