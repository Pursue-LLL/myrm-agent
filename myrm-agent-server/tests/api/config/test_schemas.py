"""Test ConfigKey schema and related models."""

import typing

from app.schemas.config import ConfigKey


def test_whatsapp_credentials_in_config_key() -> None:
    """Verify whatsappCredentials is a valid ConfigKey."""
    config_keys = typing.get_args(ConfigKey)
    assert "whatsappCredentials" in config_keys, "whatsappCredentials must be in ConfigKey enum"


def test_all_credentials_keys_present() -> None:
    """Verify all expected credential keys are present in ConfigKey."""
    config_keys = typing.get_args(ConfigKey)
    required_credential_keys = [
        "feishuCredentials",
        "dingtalkCredentials",
        "slackCredentials",
        "qqCredentials",
        "discordCredentials",
        "wecomCredentials",
        "wechatCredentials",
        "teamsCredentials",
        "matrixCredentials",
        "telegramCredentials",
        "googlechatCredentials",
        "whatsappCredentials",
        "smsCredentials",
    ]
    for key in required_credential_keys:
        assert key in config_keys, f"{key} must be in ConfigKey enum"
