"""Every config key is sealed at rest, or is listed here as a row that holds no secret.

[INPUT]
app.schemas.config::ConfigKey (POS: every key the config API accepts)
app.services.config.encryption::is_sensitive_config (POS: the hand-written list of keys sealed at rest)

[OUTPUT]
That a key cannot be stored in plaintext just because nobody classified it: a new ``ConfigKey`` fails here until it is
added to ``SENSITIVE_CONFIG_KEYS`` or to the list below, and a listed key that later becomes sensitive fails here too.

[POS]
The sealed list is written by hand, and ``backupSync`` and ``voice`` were both missing from it while they held a WebDAV
password, an S3 secret and speech API keys. The archive policy (``table_policy``) and the re-entry notices follow the
same list, so one forgotten key leaks through all three.
"""

from __future__ import annotations

from typing import get_args

from app.schemas.config import ConfigKey
from app.services.config.encryption import is_sensitive_config

# Preferences, model choices, schedules and feature switches: nothing in these rows opens an account or costs money.
_PLAIN_ROWS: frozenset[str] = frozenset(
    {
        "defaultModelConfig",
        "customModelInfo",
        "chatSettings",
        "commands",
        "channels",
        "securityConfig",
        "channelInstances",
        "channelLabels",
        "onboarding",
        "secondBrainPreset",
        "budget_policy",
        "companion_config",
        "securityDashboardSettings",
        "orgModelPolicy",
        "extensionClipAgent",
        "user_progression",
    }
)

# Preferences plus one optional key (``privacyRouting.localApiKey``, the key of a model endpoint the user runs): the row
# is read and written as one document, so sealing it whole would make archives without a passphrase drop the preferences.
_PLAIN_ROWS_WITH_AN_OPTIONAL_KEY: frozenset[str] = frozenset({"personalSettings"})


def test_every_config_key_is_sealed_or_listed_as_holding_no_secret() -> None:
    unsealed = {key for key in get_args(ConfigKey) if not is_sensitive_config(key)}
    expected = _PLAIN_ROWS | _PLAIN_ROWS_WITH_AN_OPTIONAL_KEY

    unclassified, stale = sorted(unsealed - expected), sorted(expected - unsealed)

    assert not unclassified, (
        f"Stored in plaintext and not classified: {unclassified}. Add each to SENSITIVE_CONFIG_KEYS (and to "
        "table_policy.CARRIED_SENSITIVE_CONFIG_KEYS when it should travel in a passphrase-protected archive) if its value "
        "can hold a credential, otherwise to _PLAIN_ROWS in this test."
    )
    assert not stale, f"Listed here but sealed, or no longer a config key: {stale}. Remove them from this test."
