"""Fixtures of the enterprise TLS unit tests, which opt in with ``usefixtures("pristine_tls")``.

A fixture that sets the toggle or installs the policy asks for ``pristine_tls`` by name, so the slate is clean before it
runs; ``usefixtures`` alone would order it after the autouse ones.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.mcp_testkit.tls_pki import generate_inspection_chain
from tests.support.tls_loopback import restore_standard_tls, stand_in_system_trust


@pytest.fixture
def pristine_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start the test with the standard builders and no TLS environment, and restore both afterwards."""
    restore_standard_tls(monkeypatch)


@pytest.fixture
def ca_file(tmp_path: Path) -> Path:
    return generate_inspection_chain(tmp_path).ca_cert


@pytest.fixture
def other_ca_file(tmp_path: Path) -> Path:
    """A CA other than ``ca_file``'s."""
    directory = tmp_path / "other"
    directory.mkdir()
    return generate_inspection_chain(directory).ca_cert


@pytest.fixture
def inspectable_system_trust(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand a plain context in for the system-store one, whose loaded CAs cannot be listed (``get_ca_certs`` raises)."""
    stand_in_system_trust(monkeypatch)
