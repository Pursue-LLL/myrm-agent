"""Test ConfigKey schema and related models."""

import typing

from app.schemas.config import ConfigKey, PersonalSettingsConfigValue


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


# ---------------------------------------------------------------------------
# PersonalSettingsConfigValue — suggestWorkflowMode defaults & schema metadata
# ---------------------------------------------------------------------------


def test_suggest_workflow_mode_default_false() -> None:
    """suggestWorkflowMode must default to False (single-agent gatekeeping)."""
    settings = PersonalSettingsConfigValue()
    assert settings.suggestWorkflowMode is False


def test_suggest_workflow_mode_schema_metadata() -> None:
    """suggestWorkflowMode must carry correct x-ui-section and x-ui-group."""
    schema = PersonalSettingsConfigValue.model_json_schema()
    props = schema["properties"]["suggestWorkflowMode"]
    assert props["x-ui-section"] == "preferences"
    assert props["x-ui-group"] == "advanced"


def test_suggest_workflow_mode_explicit_true() -> None:
    """Explicitly setting suggestWorkflowMode to True must be respected."""
    settings = PersonalSettingsConfigValue(suggestWorkflowMode=True)
    assert settings.suggestWorkflowMode is True


def test_personal_settings_key_in_config_key() -> None:
    """personalSettings must be a valid ConfigKey."""
    config_keys = typing.get_args(ConfigKey)
    assert "personalSettings" in config_keys
