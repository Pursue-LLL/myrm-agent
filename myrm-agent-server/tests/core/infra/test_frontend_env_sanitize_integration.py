"""Integration test: verify FrontendLauncher.start() strips toxic env vars.

Patches os.environ with toxic variables, then intercepts subprocess.Popen
to capture the actual `env` dict passed to the Node.js process. Verifies
that all _TOXIC_NODE_ENV_VARS are removed while safe vars are preserved.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from app.core.infra.frontend_launcher import (
    _TOXIC_NODE_ENV_VARS,
    FrontendLauncher,
)

INJECTED_TOXIC: dict[str, str] = {
    "NODE_OPTIONS": "--max-old-space-size=100",
    "HTTP_PROXY": "http://evil.proxy:8080",
    "HTTPS_PROXY": "https://evil.proxy:8443",
    "http_proxy": "http://lower.proxy",
    "LD_PRELOAD": "/tmp/evil.so",
    "DYLD_INSERT_LIBRARIES": "/tmp/evil.dylib",
    "NODE_TLS_REJECT_UNAUTHORIZED": "0",
    "SSLKEYLOGFILE": "/tmp/keys.log",
    "ALL_PROXY": "socks5://evil:1080",
}

SAFE_VARS: dict[str, str] = {
    "PATH": "/usr/bin:/usr/local/bin",
    "HOME": "/home/testuser",
    "LANG": "en_US.UTF-8",
    "TERM": "xterm-256color",
}


class TestFrontendLauncherEnvIntegration:
    """Intercept Popen to verify the env dict passed to Node.js."""

    def _capture_popen_env(self) -> dict[str, str]:
        """Run FrontendLauncher.start() with patched deps, return the env."""
        captured_env: dict[str, str] = {}

        def fake_popen(args: list[str], **kwargs: object) -> MagicMock:
            captured_env.update(kwargs.get("env", {}))  # type: ignore[arg-type]
            mock_proc = MagicMock()
            mock_proc.pid = 99999
            mock_proc.stdout = MagicMock()
            mock_proc.stderr = MagicMock()
            mock_proc.stdin = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.returncode = None
            return mock_proc

        fake_environ = {**SAFE_VARS, **INJECTED_TOXIC}

        launcher = FrontendLauncher(
            frontend_port=13000,
            api_port=25808,
        )

        with (
            patch.dict(os.environ, fake_environ, clear=True),
            patch("app.core.infra.frontend_launcher.check_build_artifacts"),
            patch("app.core.infra.frontend_launcher.ensure_standalone_assets"),
            patch("app.core.infra.frontend_launcher.patch_nextjs_rewrites"),
            patch("app.core.infra.frontend_launcher.find_available_port", return_value=13000),
            patch("app.core.infra.frontend_launcher._wait_for_health", return_value=True),
            patch("subprocess.Popen", side_effect=fake_popen),
        ):
            launcher.start()

        return captured_env

    def test_toxic_vars_stripped(self) -> None:
        env = self._capture_popen_env()
        for var in INJECTED_TOXIC:
            assert var not in env, f"Toxic var {var} should be stripped from env"

    def test_all_toxic_list_stripped(self) -> None:
        env = self._capture_popen_env()
        for var in _TOXIC_NODE_ENV_VARS:
            assert var not in env, f"{var} from _TOXIC_NODE_ENV_VARS should be stripped"

    def test_safe_vars_preserved(self) -> None:
        env = self._capture_popen_env()
        for key, val in SAFE_VARS.items():
            assert env.get(key) == val, f"Safe var {key} should be preserved"

    def test_launcher_vars_injected(self) -> None:
        env = self._capture_popen_env()
        assert env["PORT"] == "13000"
        assert env["NODE_ENV"] == "production"
        assert env["API_PORT"] == "25808"
        assert env["HOSTNAME"] == "127.0.0.1"

    def test_env_is_complete(self) -> None:
        env = self._capture_popen_env()
        expected_keys = set(SAFE_VARS.keys()) | {"PORT", "NODE_ENV", "API_HOST", "API_PORT", "HOSTNAME"}
        assert expected_keys.issubset(env.keys())
        toxic_leaked = set(INJECTED_TOXIC.keys()) & set(env.keys())
        assert toxic_leaked == set(), f"Toxic vars leaked: {toxic_leaked}"
