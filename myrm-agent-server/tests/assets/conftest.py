"""Fixtures for the tests of the prebuilt skill scripts.

[INPUT]
- tests/support/self_signed_tls.py: the loopback certificate
- tests/support/email_skill_script.py: where the imap-smtp-email script directory is

[OUTPUT]
- listener_tls: server TLS context and the certificate file a client has to trust to accept it
- skill_modules: ``email_manager`` and ``mail_client`` importable as they are when the script runs, forgotten afterwards

[POS]
Shared fixtures of ``tests/assets``; the skill scripts run from their own directory, so a test that imports them
in process has to put that directory on ``sys.path`` and must not leave the modules behind.
"""

from __future__ import annotations

import ssl
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.email_skill_script import SKILL_SCRIPTS
from tests.support.self_signed_tls import self_signed_certificate

_SKILL_MODULES = ("email_manager", "mail_client")


@pytest.fixture
def listener_tls(tmp_path: Path) -> tuple[ssl.SSLContext, Path]:
    cert, key = self_signed_certificate(tmp_path)
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(cert, key)
    return context, cert


@pytest.fixture
def skill_modules(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.syspath_prepend(str(SKILL_SCRIPTS))
    yield
    for name in [name for name in sys.modules if name.partition(".")[0] in _SKILL_MODULES]:
        del sys.modules[name]
