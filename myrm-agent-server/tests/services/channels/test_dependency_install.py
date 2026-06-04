"""Unit tests for channel lazy dependency installation."""

from __future__ import annotations

from unittest.mock import patch

from app.channels.types import ChannelIssue, IssueKind, IssueSeverity
from app.services.channels.dependency_install import (
    _features_for_channel,
    install_channel_dependencies,
)


def test_features_for_matrix_e2ee_from_issue_fix() -> None:
    issues = [
        ChannelIssue(
            kind=IssueKind.DEPENDENCY,
            severity=IssueSeverity.ERROR,
            message="E2EE deps missing",
            fix="uv sync --extra matrix --extra matrix-e2ee",
        )
    ]
    assert _features_for_channel("matrix", issues) == (
        "platform.matrix",
        "platform.matrix-e2ee",
    )


def test_install_matrix_calls_ensure_and_reload() -> None:
    with (
        patch("app.services.channels.dependency_install.ensure") as mock_ensure,
        patch("app.services.channels.dependency_install.clear_cache") as mock_clear,
        patch("app.services.channels.dependency_install._reload_matrix_imports") as mock_reload,
    ):
        ok, message = install_channel_dependencies("matrix", [])

    assert ok is True
    assert "installed" in message.lower()
    mock_ensure.assert_called_once_with("platform.matrix", prompt=False)
    mock_clear.assert_called_once()
    mock_reload.assert_called_once()
