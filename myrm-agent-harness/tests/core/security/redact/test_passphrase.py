"""passphrase: a credential noun in every shape the redactor detects credentials in.

Backup and key tooling calls its secret a passphrase: ``BORG_PASSPHRASE`` in a backup script, ``PASSPHRASE=`` for
duplicity, ``gpg --batch --passphrase``, ``ssh_passphrase`` in a config file or a JSON settings dump. The word has no
``key``, ``token``, ``secret`` or ``password`` in it, so each detector needs it by name. The keep-list pins what a
reader still needs to see: variable references, hint and flag fields, and prose.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text

_VALUE = "correct-horse-91-Zk3fQ9xL"


# shape -> (text, the name that must stay visible)
_SHAPES: dict[str, tuple[str, str]] = {
    "json": (json.dumps({"ssh_passphrase": _VALUE, "host": "backup.example"}), "ssh_passphrase"),
    "json-camel": (json.dumps({"keyStorePassPhrase": _VALUE}), "keyStorePassPhrase"),
    "json-in-json": (json.dumps({"output": json.dumps({"passphrase": _VALUE})}), "passphrase"),
    "repr": (f"E   assert {{'passphrase': '{_VALUE}'}} == {{}}", "passphrase"),
    "env-export": (f"export BORG_PASSPHRASE='{_VALUE}'\nborg create ::{{now}} ~/Documents", "BORG_PASSPHRASE"),
    "env-inline": (f"PASSPHRASE={_VALUE} duplicity /home s3://bucket", "PASSPHRASE"),
    "env-split-word": (f"export PASS_PHRASE={_VALUE}", "PASS_PHRASE"),
    "env-dotted": (f"app.ssh.passphrase={_VALUE}", "app.ssh.passphrase"),
    "yaml": (f"vault_passphrase: {_VALUE}", "vault_passphrase"),
    "yaml-quoted": (f'ssh_passphrase: "{_VALUE}"', "ssh_passphrase"),
    "cli-space": (f"gpg --batch --passphrase {_VALUE} -d secrets.gpg", "--passphrase"),
    "cli-equals": (f"gpg --batch --passphrase={_VALUE} -d secrets.gpg", "--passphrase"),
    "cli-hyphenated": (f"tool --pass-phrase {_VALUE}", "--pass-phrase"),
    "url-query": (f"https://backup.example/restore?passphrase={_VALUE}&dest=/tmp", "passphrase"),
}


class TestPassphraseIsMasked:
    @pytest.mark.parametrize("shape", _SHAPES)
    def test_value_is_masked_and_name_is_kept(self, shape: str) -> None:
        text, name = _SHAPES[shape]
        out = redact_sensitive_text(text)
        assert _VALUE not in out
        assert name in out

    def test_short_value_is_masked_completely(self) -> None:
        assert redact_sensitive_text("export BORG_PASSPHRASE=hunter2hunter") == "export BORG_PASSPHRASE=***"


class TestPassphraseKeepList:
    @pytest.mark.parametrize(
        "text",
        [
            "export BORG_PASSPHRASE=${BORG_PASSPHRASE}",
            "vault_passphrase: ${VAULT_PASSPHRASE:?set it in .env}",
            'export BORG_PASSCOMMAND="cat $HOME/.borg-passphrase"',
            json.dumps({"passphraseHint": "At least 8 characters.", "passphrase_required": "Enter it to continue."}),
            "Enter your passphrase to continue. The passphrase is never stored.",
        ],
    )  # fmt: skip
    def test_text_stays_readable(self, text: str) -> None:
        assert redact_sensitive_text(text) == text
