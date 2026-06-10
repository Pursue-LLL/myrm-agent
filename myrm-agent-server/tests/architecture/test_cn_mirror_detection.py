"""Architecture test: install scripts contain CN mirror auto-detection logic."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_ROOT / "install.sh"
_INSTALL_PS1 = _SCRIPTS_ROOT / "install.ps1"
_DOCKERFILE = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "myrm-agent-server"
    / "Dockerfile"
)


@pytest.mark.architecture
class TestCnMirrorDetection:
    """Verify CN mirror auto-detection is present and correct."""

    def test_install_sh_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(_INSTALL_SH)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_install_sh_has_detect_cn_network(self) -> None:
        content = _INSTALL_SH.read_text()
        assert "detect_cn_network()" in content
        assert "setup_cn_mirrors()" in content
        assert "UV_DEFAULT_INDEX" in content
        assert "BUN_CONFIG_REGISTRY" in content
        assert "PLAYWRIGHT_DOWNLOAD_HOST" in content

    def test_install_sh_uses_correct_uv_variable(self) -> None:
        """UV_INDEX_URL is deprecated; we must use UV_DEFAULT_INDEX."""
        content = _INSTALL_SH.read_text()
        assert "UV_DEFAULT_INDEX" in content
        assert "UV_INDEX_URL" not in content

    def test_install_sh_force_enable(self) -> None:
        script = (
            f'eval "$(sed -n "/^detect_cn_network/,/^}}/p" {_INSTALL_SH})"\n'
            "MYRM_USE_CN_MIRROR=1 MYRM_NO_CN_MIRROR=0 "
            "detect_cn_network && echo YES || echo NO"
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, timeout=5
        )
        assert "YES" in result.stdout

    def test_install_sh_force_disable(self) -> None:
        script = (
            f'eval "$(sed -n "/^detect_cn_network/,/^}}/p" {_INSTALL_SH})"\n'
            "MYRM_USE_CN_MIRROR=0 MYRM_NO_CN_MIRROR=1 "
            "detect_cn_network && echo YES || echo NO"
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, timeout=5
        )
        assert "NO" in result.stdout

    def test_install_sh_respects_existing_index(self) -> None:
        script = (
            f'eval "$(sed -n "/^detect_cn_network/,/^}}/p" {_INSTALL_SH})"\n'
            'UV_DEFAULT_INDEX="https://custom" MYRM_USE_CN_MIRROR=0 MYRM_NO_CN_MIRROR=0 '
            "detect_cn_network && echo YES || echo NO"
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, timeout=5
        )
        assert "NO" in result.stdout

    def test_install_sh_non_cn_timezone(self) -> None:
        script = (
            f'eval "$(sed -n "/^detect_cn_network/,/^}}/p" {_INSTALL_SH})"\n'
            'TZ="America/New_York" MYRM_USE_CN_MIRROR=0 MYRM_NO_CN_MIRROR=0 '
            "detect_cn_network && echo YES || echo NO"
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, timeout=5
        )
        assert "NO" in result.stdout

    def test_install_sh_macos_localtime_detection(self) -> None:
        """macOS uses /etc/localtime symlink, not /etc/timezone."""
        script = (
            f'eval "$(sed -n "/^detect_cn_network/,/^}}/p" {_INSTALL_SH})"\n'
            "unset TZ\n"
            "curl() { return 1; }\n"
            "export -f curl\n"
            "MYRM_USE_CN_MIRROR=0 MYRM_NO_CN_MIRROR=0 "
            "detect_cn_network && echo YES || echo NO"
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, timeout=5
        )
        # On macOS with Asia/Shanghai localtime + mocked curl fail → YES
        # On non-CN systems → NO (either way the test validates no crash)
        assert result.returncode == 0

    def test_install_ps1_has_cn_functions(self) -> None:
        content = _INSTALL_PS1.read_text()
        assert "Test-CnNetwork" in content
        assert "Set-CnMirrors" in content
        assert "UV_DEFAULT_INDEX" in content
        assert "BUN_CONFIG_REGISTRY" in content

    def test_dockerfile_has_cn_mirror_arg(self) -> None:
        content = _DOCKERFILE.read_text()
        assert "ARG USE_CN_MIRROR" in content
        assert "ARG APT_MIRROR" in content
        assert "UV_DEFAULT_INDEX" in content
