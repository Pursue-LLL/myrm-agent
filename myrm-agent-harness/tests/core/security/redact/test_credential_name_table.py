"""The credential names every exit reads: ``secret`` as the last word, ``passcode``, and the names that stay readable.

``api_secret`` and ``jwt_secret`` name a credential like ``client_secret`` does, ``passcode`` like ``passphrase`` does.
``pwd`` is not a credential name: it is also the working directory (``PWD``, ``cwd_pwd``), so it is masked only in the
variables known by name (``MYSQL_PWD``).
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text, structured_fields
from myrm_agent_harness.core.security.redact.structured_fields import is_secret_field_name
from myrm_agent_harness.infra.tracing.sanitizer import TraceSpanSanitizer

_VALUE = "x9Kq2LmT8vB4nR7s"


@pytest.mark.parametrize(
    "name",
    [
        "api_secret", "apiSecret", "api-secret", "jwt_secret", "JWT_SECRET", "webhookSecret", "oauth.secret",
        "passcode", "adminPasscode", "admin_passcode", "ADMIN_PASSCODE", "pass_code", "pass-code",
    ],
)  # fmt: skip
def test_the_name_is_a_credential(name: str) -> None:
    assert is_secret_field_name(name)


@pytest.mark.parametrize(
    "name",
    ["secretary", "secret_name", "secrets_dir", "secret_ref", "passcodes", "pwd", "cwd_pwd", "OLDPWD", "compass", "bypass"],
)  # fmt: skip
def test_the_name_is_not_a_credential(name: str) -> None:
    assert not is_secret_field_name(name)


@pytest.mark.parametrize("key", ["api_secret", "jwtSecret", "passcode", "ADMIN_PASSCODE"])
def test_a_json_member_with_the_name_is_masked(key: str) -> None:
    written = redact_sensitive_text(json.dumps({"host": "db.internal", key: _VALUE}))

    assert _VALUE not in written
    assert "db.internal" in written


@pytest.mark.parametrize("name", ["ADMIN_PASSCODE", "ADMIN_PASS_CODE", "admin_passcode"])
@pytest.mark.parametrize("shape", ["{name}={value}", "export {name}='{value}'", "environment:\n  {name}: {value}"])
def test_an_assignment_to_a_passcode_variable_is_masked(name: str, shape: str) -> None:
    text = shape.replace("{name}", name).replace("{value}", _VALUE)

    assert redact_sensitive_text(text) == text.replace(_VALUE, "***")


@pytest.mark.parametrize(
    "text",
    [
        json.dumps({"is_secret": "true", "top_secret": "classified"}),
        json.dumps({"webhookSecret": "Webhook Secret"}),
        "PWD=/home/user/project",
        "cwd_pwd=/srv/app",
        "ADMIN_PASSCODE_FILE=/run/secrets/admin",
        "ADMIN_PASSCODE=${ADMIN_PASSCODE}",
    ],
)  # fmt: skip
def test_a_label_a_path_and_a_reference_stay_readable(text: str) -> None:
    assert redact_sensitive_text(text) == text


@pytest.mark.parametrize("key", ["db_passwd", "ssh_passphrase", "adminPasscode", "jwt_secret", "api_secret"])
def test_the_trace_api_withholds_the_value_of_every_credential_name(key: str) -> None:
    written = str(TraceSpanSanitizer().sanitize_payload({"args": {key: _VALUE, "host": "db.internal"}}))

    assert _VALUE not in written
    assert "db.internal" in written


def test_a_name_too_long_to_be_a_field_is_judged_without_being_kept() -> None:
    """The verdicts are cached for the names a payload repeats; a long key is a value in disguise and must not stay alive."""
    before = structured_fields._cached_secret_field_name.cache_info()

    assert not is_secret_field_name("x" * 500 + "_password")
    assert not is_secret_field_name("y" * 500 + "_length")

    after = structured_fields._cached_secret_field_name.cache_info()
    assert (after.hits, after.misses) == (before.hits, before.misses)
