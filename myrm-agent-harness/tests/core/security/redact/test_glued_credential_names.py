"""Credential names that run their words together: ``PGPASSWORD``, ``SSHPASS``, ``MYSQL_PWD``.

Database and SSH clients read their password from an environment variable whose name does not separate the words.
The key guard asks for a credential word at a word boundary, which keeps ``MYTOKEN`` and ``tokenizer`` out, so these
names fell through in an ``export`` line, a compose file and a settings dump while ``DB_PASSWORD`` was masked. One
policy covers them everywhere: a name that ends in ``password``, ``passwd`` or ``passphrase`` is a credential
however it is spelled, and ``SSHPASS`` and ``MYSQL_PWD`` are credentials by name.
"""

from __future__ import annotations

import json
import re

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.toolkits.code_execution.security.env_isolation import FORBIDDEN_EXACT_KEYS

_VALUE = "correct-horse-91-Zk3fQ9xL"

_NAMES = ("PGPASSWORD", "SSHPASS", "MYSQL_PWD", "DBPASSWORD", "BACKUPPASSPHRASE")

_SHAPES: dict[str, str] = {
    "export": "export {name}='{value}'\npsql -h db.internal -U app",
    "inline": "{name}={value} psql -h db.internal -U app",
    "yaml": "environment:\n  {name}: {value}\n  TZ: UTC",
    "dotenv": "# database\n{name}={value}\nPORT=5432",
    "json": json.dumps({"{name}": "{value}", "host": "db.internal"}),
}


class TestGluedNamesAreMasked:
    @pytest.mark.parametrize("shape", _SHAPES)
    @pytest.mark.parametrize("name", _NAMES)
    def test_value_is_replaced_and_everything_else_is_kept(self, name: str, shape: str) -> None:
        text = _SHAPES[shape].replace("{name}", name).replace("{value}", _VALUE)
        assert redact_sensitive_text(text) == text.replace(_VALUE, "***")

    @pytest.mark.parametrize("name", ["pgpassword", "PgPassword", "mysql_pwd", "sshpass"])
    def test_spelling_does_not_matter(self, name: str) -> None:
        assert redact_sensitive_text(f"{name}={_VALUE}") == f"{name}=***"

    def test_a_name_inside_a_longer_dotted_or_prefixed_key_is_masked(self) -> None:
        text = f"app.db.MYSQL_PWD={_VALUE}\nCI_SSHPASS={_VALUE}"
        assert redact_sensitive_text(text) == text.replace(_VALUE, "***")


class TestNamesThatOnlyLookSimilarAreKept:
    @pytest.mark.parametrize(
        "text",
        [
            "PWD=/home/user/project",
            "OLDPWD=/tmp/build",
            "escaped_pwd = re.escape(pwd)",
            "cwd_pwd=/srv/app",
            "PGPASSWORD_FILE=/run/secrets/pg_password",
            "SSHPASS_FILE=/run/secrets/ssh",
            "PASSWORDLESS=true",
            "export PGPASSWORD=${PGPASSWORD}",
            "MYSQL_PWD=$MYSQL_ROOT_PASSWORD",
            "environment:\n  PGPASSWORD: ${PGPASSWORD:?set it in .env}",
            "sshpass -e ssh deploy@host.example",
            json.dumps({"PGPASSFILE": "/home/app/.pgpass", "pwd": "/home/app"}),
        ],
    )  # fmt: skip
    def test_text_stays_readable(self, text: str) -> None:
        assert redact_sensitive_text(text) == text

    def test_a_word_that_merely_ends_a_longer_word_is_not_a_credential_name(self) -> None:
        assert redact_sensitive_text("MYTOKEN=abc123def456") == "MYTOKEN=abc123def456"


_PASSWORD_CLASS_NAMES = sorted(k for k in FORBIDDEN_EXACT_KEYS if re.search(r"(?:PASSWORD|PASSWD|PASSPHRASE)$", k))


class TestEveryNameTheChildEnvironmentStripsIsMasked:
    """A password-class variable that a child process may not inherit is also never shown by a tool."""

    def test_the_list_is_not_empty(self) -> None:
        assert {"PGPASSWORD", "DB_PASSWORD", "REDIS_PASSWORD"} <= set(_PASSWORD_CLASS_NAMES)

    @pytest.mark.parametrize("name", _PASSWORD_CLASS_NAMES)
    def test_value_is_masked(self, name: str) -> None:
        assert redact_sensitive_text(f"{name}={_VALUE}") == f"{name}=***"
