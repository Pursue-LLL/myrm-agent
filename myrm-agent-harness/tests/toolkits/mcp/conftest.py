"""Shared fixtures for the MCP toolkit tests."""

from __future__ import annotations

import pytest

from tests.support.mcp_testkit.tls_pki import TlsPki, generate_tls_pki


@pytest.fixture(autouse=True)
def _strict_tls_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The enterprise network compatibility setting is off unless a test turns it on, whatever the shell exports."""
    monkeypatch.delenv("MYRM_TLS_STRICT", raising=False)


@pytest.fixture(scope="session")
def pki(tmp_path_factory: pytest.TempPathFactory) -> TlsPki:
    """One throwaway CA / server / client PKI shared by every live TLS test in the session."""
    return generate_tls_pki(tmp_path_factory.mktemp("mcp_live_pki"))
