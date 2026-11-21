"""DomainAllowlist matching and the install_domain_filter wiring."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.domain_filter import (
    DomainAllowlist,
    build_csp_meta_script,
    build_init_script,
    install_domain_filter,
)


def _registered_scripts(context: MagicMock) -> list[str]:
    """The init scripts registered on the context, in registration order."""
    return [call.args[0] for call in context.add_init_script.await_args_list]


# =============================================================================
# DomainAllowlist
# =============================================================================


class TestDomainAllowlist:
    """Test DomainAllowlist class."""

    def test_init(self) -> None:
        """Test DomainAllowlist initialization."""
        allowlist = DomainAllowlist(patterns=("example.com", "*.github.com"))

        assert allowlist.patterns == ("example.com", "*.github.com")

    def test_from_strings(self) -> None:
        """Test from_strings factory method."""
        allowlist = DomainAllowlist.from_strings(["  Example.COM  ", "*.GitHub.com", ""])

        assert allowlist.patterns == ("example.com", "*.github.com")

    def test_from_strings_empty_list(self) -> None:
        """Test from_strings with empty list."""
        allowlist = DomainAllowlist.from_strings([])

        assert allowlist.patterns == ()
        assert allowlist.is_empty

    def test_from_strings_only_whitespace(self) -> None:
        """Test from_strings filters out whitespace-only strings."""
        allowlist = DomainAllowlist.from_strings(["  ", "\t", "\n", ""])

        assert allowlist.patterns == ()

    def test_is_empty_true(self) -> None:
        """Test is_empty returns True for empty allowlist."""
        allowlist = DomainAllowlist(patterns=())

        assert allowlist.is_empty is True

    def test_is_empty_false(self) -> None:
        """Test is_empty returns False for non-empty allowlist."""
        allowlist = DomainAllowlist(patterns=("example.com",))

        assert allowlist.is_empty is False

    def test_is_allowed_exact_match(self) -> None:
        """Test exact domain match."""
        allowlist = DomainAllowlist(patterns=("example.com",))

        assert allowlist.is_allowed("example.com") is True
        assert allowlist.is_allowed("EXAMPLE.COM") is True
        assert allowlist.is_allowed("other.com") is False

    def test_is_allowed_wildcard_subdomain(self) -> None:
        """Test wildcard subdomain match."""
        allowlist = DomainAllowlist(patterns=("*.example.com",))

        assert allowlist.is_allowed("example.com") is True
        assert allowlist.is_allowed("www.example.com") is True
        assert allowlist.is_allowed("api.example.com") is True
        assert allowlist.is_allowed("other.com") is False

    def test_is_allowed_wildcard_nested_subdomain(self) -> None:
        """Test wildcard match for nested subdomains."""
        allowlist = DomainAllowlist(patterns=("*.github.com",))

        assert allowlist.is_allowed("github.com") is True
        assert allowlist.is_allowed("api.github.com") is True
        assert allowlist.is_allowed("foo.bar.github.com") is True
        assert allowlist.is_allowed("raw.githubusercontent.com") is False

    def test_is_allowed_multiple_patterns(self) -> None:
        """Test multiple patterns."""
        allowlist = DomainAllowlist(patterns=("example.com", "*.github.com", "google.com"))

        assert allowlist.is_allowed("example.com") is True
        assert allowlist.is_allowed("api.github.com") is True
        assert allowlist.is_allowed("google.com") is True
        assert allowlist.is_allowed("facebook.com") is False

    def test_is_allowed_case_insensitive(self) -> None:
        """Test case-insensitive matching."""
        allowlist = DomainAllowlist.from_strings(["Example.COM"])

        assert allowlist.is_allowed("example.com") is True
        assert allowlist.is_allowed("EXAMPLE.COM") is True
        assert allowlist.is_allowed("Example.Com") is True

    def test_is_blocked_same_matching_semantics_as_allowed(self) -> None:
        """is_blocked mirrors is_allowed pattern matching (exact + wildcard)."""
        blocklist = DomainAllowlist.from_strings(["huggingface.co", "*.huggingface.co", "hf.co"])

        assert blocklist.is_blocked("huggingface.co") is True
        assert blocklist.is_blocked("datasets.huggingface.co") is True
        assert blocklist.is_blocked("hf.co") is True
        assert blocklist.is_blocked("example.com") is False
        assert blocklist.is_blocked("") is False

    def test_is_blocked_empty_patterns(self) -> None:
        """is_blocked returns False for an empty blocklist."""
        blocklist = DomainAllowlist.from_strings([])

        assert blocklist.is_blocked("huggingface.co") is False


# =============================================================================
# install_domain_filter
# =============================================================================


@pytest.mark.asyncio
async def test_install_domain_filter_empty_allowlist() -> None:
    """Test install_domain_filter skips for empty allowlist."""
    context = MagicMock()
    context.route = AsyncMock()
    context.add_init_script = AsyncMock()
    context.on = MagicMock()

    allowlist = DomainAllowlist(patterns=())

    await install_domain_filter(context, allowlist)

    context.route.assert_not_called()
    context.add_init_script.assert_not_called()


@pytest.mark.asyncio
async def test_install_domain_filter_with_patterns() -> None:
    """Test install_domain_filter installs all four layers."""
    context = MagicMock()
    context.route = AsyncMock()
    context.add_init_script = AsyncMock()
    context.on = MagicMock()

    allowlist = DomainAllowlist(patterns=("example.com",))

    await install_domain_filter(context, allowlist)

    context.route.assert_called_once()
    assert _registered_scripts(context) == [build_csp_meta_script(allowlist), build_init_script()]

    assert context.on.call_count == 1
    call_args = context.on.call_args
    assert call_args[0][0] == "page"
    assert callable(call_args[0][1])


@pytest.mark.asyncio
async def test_install_domain_filter_without_cdp_audit() -> None:
    """Test install_domain_filter with CDP audit disabled."""
    context = MagicMock()
    context.route = AsyncMock()
    context.add_init_script = AsyncMock()
    context.on = MagicMock()

    allowlist = DomainAllowlist(patterns=("example.com",))

    await install_domain_filter(context, allowlist, enable_cdp_audit=False)

    context.route.assert_called_once()
    assert _registered_scripts(context) == [build_csp_meta_script(allowlist), build_init_script()]
    context.on.assert_not_called()


# =============================================================================
# Integration test with mocked context
# =============================================================================


@pytest.mark.asyncio
async def test_domain_filter_full_workflow() -> None:
    """Test complete domain filtering workflow."""
    context = MagicMock()
    context.route = AsyncMock()
    context.add_init_script = AsyncMock()
    context.on = MagicMock()

    patterns = ["example.com", "*.github.com", "api.openai.com"]
    allowlist = DomainAllowlist.from_strings(patterns)

    assert not allowlist.is_empty
    assert allowlist.is_allowed("example.com")
    assert allowlist.is_allowed("api.github.com")
    assert allowlist.is_allowed("api.openai.com")
    assert not allowlist.is_allowed("facebook.com")

    await install_domain_filter(context, allowlist, enable_cdp_audit=True)

    context.route.assert_called_once()
    assert _registered_scripts(context) == [build_csp_meta_script(allowlist), build_init_script()]
    assert context.on.call_count == 1


# =============================================================================
# Edge cases
# =============================================================================


def test_allowlist_frozen() -> None:
    """Test DomainAllowlist is frozen (immutable)."""
    allowlist = DomainAllowlist(patterns=("example.com",))

    with pytest.raises(FrozenInstanceError):
        allowlist.patterns = ("hacked.com",)  # type: ignore[misc]


def test_allowlist_empty_patterns() -> None:
    """Test empty patterns tuple."""
    allowlist = DomainAllowlist(patterns=())

    assert allowlist.is_empty
    assert not allowlist.is_allowed("example.com")


def test_is_allowed_subdomain_not_matching() -> None:
    """Test subdomain of non-wildcard pattern is rejected."""
    allowlist = DomainAllowlist(patterns=("example.com",))

    assert allowlist.is_allowed("example.com") is True
    assert allowlist.is_allowed("www.example.com") is False


def test_is_allowed_wildcard_exact_bare_domain() -> None:
    """Test *.example.com matches bare domain example.com."""
    allowlist = DomainAllowlist(patterns=("*.example.com",))

    assert allowlist.is_allowed("example.com") is True
