"""The WebUI startup banner tells a remote operator what a reverse proxy in front of the server must pass on.

A proxy on the same machine that forwards neither the public Host header nor the client address is
indistinguishable from a local client, so the banner has to name that requirement where it recommends a proxy.
"""

from __future__ import annotations

import pytest

from app.core.infra import frontend_launcher
from app.services.webui.temp_token import temp_token_service
from app.startup.uvicorn_runner import _setup_webui_mode


@pytest.fixture(autouse=True)
def _offline_banner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the printed text is under test: no frontend process and no real setup token."""
    monkeypatch.setattr(frontend_launcher, "launch_frontend", lambda **_: None)
    monkeypatch.setattr(temp_token_service, "generate_token", lambda: "setup-token")


def test_remote_banner_names_what_the_proxy_must_pass_on(capsys: pytest.CaptureFixture[str]) -> None:
    _setup_webui_mode("0.0.0.0", 8080, remote_mode=True, no_qrcode=True, no_browser=True)

    banner = capsys.readouterr().out
    assert "Remote Mode - Authentication Required" in banner
    assert "reverse proxy (nginx/Caddy)" in banner
    assert "public Host header" in banner
    assert "X-Forwarded-For" in banner
    assert "skip login" in banner


def test_local_banner_carries_no_proxy_advice(capsys: pytest.CaptureFixture[str]) -> None:
    _setup_webui_mode("127.0.0.1", 8080, remote_mode=False, no_qrcode=True, no_browser=True)

    banner = capsys.readouterr().out
    assert "Local Mode - No authentication required" in banner
    assert "X-Forwarded-For" not in banner
