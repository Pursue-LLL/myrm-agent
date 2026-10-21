"""Unit tests for batch approval command parsing."""

from app.channels.routing.commands import (
    is_explicit_approval_command,
    parse_approval_command,
)


def test_parse_single_approve_commands() -> None:
    """Test single approval command parsing.

    The router commands module returns the three-tier
    ``ApprovalDecision`` literal (``allow_once`` / ``allow_always`` /
    ``deny``); legacy bool semantics map onto ``allow_once`` / ``deny``.
    """
    assert parse_approval_command("/approve") == "allow_once"
    assert parse_approval_command("1") == "allow_once"
    assert parse_approval_command("y") == "allow_once"
    assert parse_approval_command("yes") == "allow_once"
    assert parse_approval_command("同意") == "allow_once"

    assert parse_approval_command("/approve-always") == "allow_always"
    assert parse_approval_command("/always") == "allow_always"
    assert parse_approval_command("永远允许") == "allow_always"

    assert parse_approval_command("/deny") == "deny"
    assert parse_approval_command("2") == "deny"
    assert parse_approval_command("n") == "deny"
    assert parse_approval_command("no") == "deny"
    assert parse_approval_command("拒绝") == "deny"


def test_parse_batch_approve_commands() -> None:
    """Test batch approval command parsing with various formats."""
    result = parse_approval_command("/batch a,d,a")
    assert result == ["allow_once", "deny", "allow_once"]

    result = parse_approval_command("/batch approve,deny,approve")
    assert result == ["allow_once", "deny", "allow_once"]

    result = parse_approval_command("/batch a,r,a")
    assert result == ["allow_once", "deny", "allow_once"]

    result = parse_approval_command("/batch a, d, a")
    assert result == ["allow_once", "deny", "allow_once"]

    result = parse_approval_command("/batch aa,a,d")
    assert result == ["allow_always", "allow_once", "deny"]


def test_parse_batch_empty_or_invalid() -> None:
    """Test batch command error cases."""
    assert parse_approval_command("/batch ") is None
    assert parse_approval_command("/batch") is None
    assert parse_approval_command("/batch x,y,z") is None
    assert parse_approval_command("/batch a,invalid,d") is None


def test_parse_non_approval_commands() -> None:
    """Test non-approval content returns None."""
    assert parse_approval_command("hello") is None
    assert parse_approval_command("/stop") is None
    assert parse_approval_command("") is None


def test_is_explicit_approval_command() -> None:
    """Test explicit approval command detection."""
    assert is_explicit_approval_command("/approve") is True
    assert is_explicit_approval_command("/deny") is True
    assert is_explicit_approval_command("/batch a,d") is True
    assert is_explicit_approval_command("1") is False
    assert is_explicit_approval_command("2") is False
    assert is_explicit_approval_command("hello") is False


def test_parse_approval_case_insensitive() -> None:
    """Test command parsing is case-insensitive."""
    assert parse_approval_command("/APPROVE") == "allow_once"
    assert parse_approval_command("/Deny") == "deny"
    assert parse_approval_command("/BATCH A,D,A") == [
        "allow_once",
        "deny",
        "allow_once",
    ]
