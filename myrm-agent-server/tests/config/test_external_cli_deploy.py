"""Unit tests for external_cli deploy gate."""

from __future__ import annotations

from unittest.mock import patch

from app.config.external_cli_deploy import is_external_cli_deploy_supported


def test_external_cli_supported_in_local_mode() -> None:
    with patch("app.config.external_cli_deploy.is_local_mode", return_value=True):
        assert is_external_cli_deploy_supported() is True


def test_external_cli_unsupported_in_sandbox_mode() -> None:
    with patch("app.config.external_cli_deploy.is_local_mode", return_value=False):
        assert is_external_cli_deploy_supported() is False
