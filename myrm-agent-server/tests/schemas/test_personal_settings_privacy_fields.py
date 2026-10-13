"""The personal settings schema keeps every privacy field the settings page saves."""

from __future__ import annotations

from app.schemas.config import PersonalSettingsConfigValue

_SAVED = {
    "privacyEnabled": True,
    "privacyS2Action": "warn",
    "privacyS3Action": "redact",
    "privacyDeepScan": False,
    "privacyCustomKeywordsS2": ["Project Falcon"],
    "privacyCustomKeywordsS3": ["vault-7"],
    "privacyCustomPatternsS2": [r"EMP-\d{6}"],
    "privacyCustomPatternsS3": [r"SEC-\d{4}"],
    "privacySensitiveToolsS2": ["browser"],
    "privacySensitiveToolsS3": ["bash"],
}


def test_saved_privacy_settings_survive_validation() -> None:
    kept = PersonalSettingsConfigValue.model_validate(_SAVED).model_dump(exclude_none=True)

    assert {key: kept.get(key) for key in _SAVED} == _SAVED


def test_privacy_settings_stay_out_of_the_schema_driven_preferences_form() -> None:
    properties = PersonalSettingsConfigValue.model_json_schema()["properties"]

    for key in _SAVED:
        assert properties[key]["x-ui-section"] == "security"
