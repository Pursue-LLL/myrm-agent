"""Test ConfigKey schema and related models."""

import typing

import pytest
from pydantic import ValidationError

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
        "wechatOfficialCredentials",
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


def test_theme_profiles_validates_recipe_shape() -> None:
    settings = PersonalSettingsConfigValue.model_validate(
        {
            "themeProfiles": [
                {
                    "id": "user-art-overlay",
                    "name": "Workspace background",
                    "layoutId": "full-bleed",
                    "fontId": "inter",
                    "builtin": False,
                    "palette": {
                        "primaryLight": "#588e95",
                        "primaryDark": "#6ba3aa",
                        "primaryHoverLight": "#4a7d84",
                        "primaryHoverDark": "#7eb5bc",
                        "primaryDarkLight": "#10505a",
                        "primaryDarkDark": "#588e95",
                        "dualAccent": False,
                    },
                    "art": {
                        "focusX": 0.5,
                        "focusY": 0.42,
                        "wash": 0.46,
                        "mediaKind": "video",
                        "assetRef": "file:video-id",
                        "posterAssetRef": "file:poster-id",
                    },
                }
            ]
        }
    )
    assert settings.themeProfiles is not None
    assert settings.themeProfiles[0].art.posterAssetRef == "file:poster-id"


def test_theme_profiles_serializes_camel_case() -> None:
    settings = PersonalSettingsConfigValue.model_validate(
        {
            "themeProfiles": [
                {
                    "id": "user-art-overlay",
                    "name": "Workspace background",
                    "layoutId": "full-bleed",
                    "fontId": "inter",
                    "builtin": False,
                    "palette": {
                        "primaryLight": "#588e95",
                        "primaryDark": "#6ba3aa",
                        "primaryHoverLight": "#4a7d84",
                        "primaryHoverDark": "#7eb5bc",
                        "primaryDarkLight": "#10505a",
                        "primaryDarkDark": "#588e95",
                        "dualAccent": False,
                    },
                    "art": {
                        "focusX": 0.5,
                        "focusY": 0.42,
                        "wash": 0.46,
                        "mediaKind": "image",
                        "assetRef": "file:hero-id",
                    },
                }
            ]
        }
    )
    dumped = settings.model_dump()
    profile = dumped["themeProfiles"][0]
    assert profile["layoutId"] == "full-bleed"
    assert profile["art"]["assetRef"] == "file:hero-id"


def test_theme_profiles_rejects_invalid_asset_ref() -> None:
    with pytest.raises(ValidationError):
        PersonalSettingsConfigValue.model_validate(
            {
                "themeProfiles": [
                    {
                        "id": "user-art-overlay",
                        "name": "Workspace background",
                        "layoutId": "full-bleed",
                        "fontId": "inter",
                        "builtin": False,
                        "palette": {
                            "primaryLight": "#588e95",
                            "primaryDark": "#6ba3aa",
                            "primaryHoverLight": "#4a7d84",
                            "primaryHoverDark": "#7eb5bc",
                            "primaryDarkLight": "#10505a",
                            "primaryDarkDark": "#588e95",
                            "dualAccent": False,
                        },
                        "art": {
                            "focusX": 0.5,
                            "focusY": 0.42,
                            "wash": 0.46,
                            "mediaKind": "image",
                            "assetRef": "https://evil.example/hero.png",
                        },
                    }
                ]
            }
        )
