"""Unit tests for channel lazy dependency installation."""

from __future__ import annotations

from unittest.mock import patch

from app.channels.types import ChannelIssue, IssueKind, IssueSeverity
from app.services.channels.dependency_install import (
    _resolve_lazy_features,
    ensure_channel_dependencies_ready,
    install_channel_dependencies,
)


def test_resolve_features_matrix_with_e2ee() -> None:
    issues = [
        ChannelIssue(
            kind=IssueKind.DEPENDENCY,
            severity=IssueSeverity.ERROR,
            message="E2EE deps missing",
            fix="uv sync --extra matrix --extra matrix-e2ee",
        )
    ]
    assert _resolve_lazy_features("matrix", issues) == (
        "platform.matrix",
        "platform.matrix-e2ee",
    )


def test_resolve_features_feishu() -> None:
    assert _resolve_lazy_features("feishu", []) == ("platform.feishu",)


def test_resolve_features_discord() -> None:
    assert _resolve_lazy_features("discord", []) == ("platform.discord",)


def test_install_matrix_calls_ensure_and_reload() -> None:
    with (
        patch("app.services.channels.dependency_install._run_install", return_value=(True, "ok")),
        patch("app.services.channels.dependency_install.clear_cache") as mock_clear,
        patch("app.services.channels.dependency_install._reload_channel_modules") as mock_reload,
        patch("app.services.channels.dependency_install.FileLock") as mock_lock_cls,
    ):
        mock_lock_cls.return_value.__enter__ = lambda self: self
        mock_lock_cls.return_value.__exit__ = lambda self, *args: None
        ok, message = install_channel_dependencies("matrix", [])

    assert ok is True
    assert message == "ok"
    mock_clear.assert_called_once()
    mock_reload.assert_called_once_with("matrix")


def test_ensure_skips_when_already_satisfied() -> None:
    with patch(
        "app.services.channels.dependency_install._features_need_install",
        return_value=False,
    ):
        ok, message = ensure_channel_dependencies_ready("discord", [])
    assert ok is True
    assert message == ""
