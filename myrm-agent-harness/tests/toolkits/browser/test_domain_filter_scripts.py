"""Page scripts the domain filter registers: the CSP meta builder (Layer 0) and the hardening script (Layer 2)."""

from __future__ import annotations

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
    assert "createElement('meta')" in script
    assert "Content-Security-Policy" in script
    assert "connect-src" in script
    assert script.strip().endswith("})();")


def test_build_csp_meta_script_waits_for_the_head_instead_of_creating_one() -> None:
    """An init script runs before the parser has made a head; making one here leaves a stray element and no policy."""
    script = build_csp_meta_script(DomainAllowlist(patterns=("example.com",)))

    assert "MutationObserver" in script
    assert "DOMContentLoaded" in script
    assert "createElement('head')" not in script


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


def test_build_csp_meta_script_empty_allowlist() -> None:
    """Test CSP with empty allowlist only allows self."""
    allowlist = DomainAllowlist(patterns=())

    script = build_csp_meta_script(allowlist)

    assert "connect-src 'self'" in script
    assert "script-src 'self'" in script
    assert "frame-src 'self'" in script
    assert "object-src 'none'" in script
    assert "example.com" not in script
    assert "github.com" not in script


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


def test_build_init_script_no_domain_logic() -> None:
    """Test script does not include domain checking (delegated to CSP)."""
    script = build_init_script()

    assert "_isAllowed" not in script
    assert "_checkUrl" not in script
    assert "_patterns" not in script
    assert "WebSocket" not in script
    assert "EventSource" not in script
    assert "sendBeacon" not in script
