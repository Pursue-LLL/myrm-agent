"""passphrase: a credential noun in every shape the redactor detects credentials in.

Backup and key tooling calls its secret a passphrase: ``BORG_PASSPHRASE`` in a backup script, ``PASSPHRASE=`` for
duplicity, ``gpg --batch --passphrase``, ``ssh_passphrase`` in a config file or a JSON settings dump. The word has no
``key``, ``token``, ``secret`` or ``password`` in it, so each detector needs it by name. The keep-list pins what a
reader still needs to see: variable references, hint and flag fields, and prose. A passphrase is hidden
completely: the output is the input with the value replaced by ``***``, not merely free of the whole value.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text

_VALUE = "correct-horse-91-Zk3fQ9xL"

_SHAPES: dict[str, str] = {
    "json": json.dumps({"ssh_passphrase": _VALUE, "host": "backup.example"}),
    "json-camel": json.dumps({"keyStorePassPhrase": _VALUE}),
    "json-in-json": json.dumps({"output": json.dumps({"passphrase": _VALUE})}),
    "repr": f"E   assert {{'passphrase': '{_VALUE}'}} == {{}}",
    "env-export": f"export BORG_PASSPHRASE='{_VALUE}'\nborg create ::{{now}} ~/Documents",
    "env-inline": f"PASSPHRASE={_VALUE} duplicity /home s3://bucket",
    "env-split-word": f"export PASS_PHRASE={_VALUE}",
    "env-dotted": f"app.ssh.passphrase={_VALUE}",
    "yaml": f"vault_passphrase: {_VALUE}",
    "yaml-quoted": f'ssh_passphrase: "{_VALUE}"',
    "cli-space": f"gpg --batch --passphrase {_VALUE} -d secrets.gpg",
    "cli-equals": f"gpg --batch --passphrase={_VALUE} -d secrets.gpg",
    "cli-hyphenated": f"tool --pass-phrase {_VALUE}",
    "url-query": f"https://backup.example/restore?passphrase={_VALUE}&dest=/tmp",
}


class TestPassphraseIsMasked:
    @pytest.mark.parametrize("shape", _SHAPES)
    def test_value_is_replaced_and_everything_else_is_kept(self, shape: str) -> None:
        text = _SHAPES[shape]
        assert redact_sensitive_text(text) == text.replace(_VALUE, "***")

    def test_short_value_is_masked_completely(self) -> None:
        assert redact_sensitive_text("export BORG_PASSPHRASE=hunter2hunter") == "export BORG_PASSPHRASE=***"


class TestPassphraseKeepList:
    @pytest.mark.parametrize(
        "text",
        [
            "export BORG_PASSPHRASE=${BORG_PASSPHRASE}",
            "gpg --batch --passphrase-file ~/.gpg-pass -d secrets.gpg",
            "gpg --batch --passphrase-fd 0 -d secrets.gpg",
            "vault_passphrase: ${VAULT_PASSPHRASE:?set it in .env}",
            'export BORG_PASSCOMMAND="cat $HOME/.borg-passphrase"',
            json.dumps({"passphraseHint": "At least 8 characters.", "passphrase_required": "Enter it to continue."}),
            "Enter your passphrase to continue. The passphrase is never stored.",
        ],
    )  # fmt: skip
    def test_text_stays_readable(self, text: str) -> None:
        assert redact_sensitive_text(text) == text
