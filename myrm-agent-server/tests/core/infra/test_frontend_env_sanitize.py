"""Tests for frontend launcher environment variable sanitization.

Verifies that _TOXIC_NODE_ENV_VARS are correctly stripped from the
environment dict before spawning the Next.js frontend process.
"""

from __future__ import annotations

import pytest

from app.core.infra.frontend_launcher import _TOXIC_NODE_ENV_VARS


class TestToxicNodeEnvVars:
    """Validate the _TOXIC_NODE_ENV_VARS constant and its pop behavior."""

    def test_is_tuple(self) -> None:
        assert isinstance(_TOXIC_NODE_ENV_VARS, tuple)

    def test_not_empty(self) -> None:
        assert len(_TOXIC_NODE_ENV_VARS) > 0

    def test_all_strings(self) -> None:
        for var in _TOXIC_NODE_ENV_VARS:
            assert isinstance(var, str), f"Expected str, got {type(var)} for {var!r}"

    def test_no_duplicates(self) -> None:
        seen: set[str] = set()
        for var in _TOXIC_NODE_ENV_VARS:
            assert var not in seen, f"Duplicate entry: {var}"
            seen.add(var)

    @pytest.mark.parametrize(
        "var",
        [
            "NODE_OPTIONS",
            "NODE_PATH",
            "NODE_TLS_REJECT_UNAUTHORIZED",
            "LD_PRELOAD",
            "DYLD_INSERT_LIBRARIES",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
        ],
    )
    def test_critical_vars_present(self, var: str) -> None:
        assert var in _TOXIC_NODE_ENV_VARS, f"{var} must be in _TOXIC_NODE_ENV_VARS"

    def test_python_vars_excluded(self) -> None:
        for var in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
            assert var not in _TOXIC_NODE_ENV_VARS, (
                f"{var} should NOT be in Node-specific list"
            )


class TestEnvPopBehavior:
    """Verify that the pop-loop correctly strips toxic vars from a dict."""

    def _build_and_sanitize(self, extra_vars: dict[str, str] | None = None) -> dict[str, str]:
        env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "PORT": "3000",
            "NODE_ENV": "production",
        }
        if extra_vars:
            env.update(extra_vars)
        for var in _TOXIC_NODE_ENV_VARS:
            env.pop(var, None)
        return env

    def test_clean_env_unchanged(self) -> None:
        env = self._build_and_sanitize()
        assert env == {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "PORT": "3000",
            "NODE_ENV": "production",
        }

    def test_toxic_vars_removed(self) -> None:
        env = self._build_and_sanitize({
            "NODE_OPTIONS": "--max-old-space-size=100",
            "HTTP_PROXY": "http://evil.proxy:8080",
            "LD_PRELOAD": "/tmp/evil.so",
        })
        assert "NODE_OPTIONS" not in env
        assert "HTTP_PROXY" not in env
        assert "LD_PRELOAD" not in env
        assert env["PATH"] == "/usr/bin"

    def test_case_sensitive_proxy_variants(self) -> None:
        env = self._build_and_sanitize({
            "http_proxy": "http://lower.proxy:8080",
            "HTTPS_PROXY": "https://upper.proxy:8443",
        })
        assert "http_proxy" not in env
        assert "HTTPS_PROXY" not in env

    def test_safe_vars_preserved(self) -> None:
        env = self._build_and_sanitize({
            "LANG": "en_US.UTF-8",
            "TERM": "xterm-256color",
            "SSLKEYLOGFILE": "/tmp/keys.log",
        })
        assert env["LANG"] == "en_US.UTF-8"
        assert env["TERM"] == "xterm-256color"
        assert "SSLKEYLOGFILE" not in env

    def test_pop_on_missing_key_is_noop(self) -> None:
        env: dict[str, str] = {"PATH": "/usr/bin"}
        for var in _TOXIC_NODE_ENV_VARS:
            env.pop(var, None)
        assert env == {"PATH": "/usr/bin"}

    def test_node_env_not_stripped(self) -> None:
        """NODE_ENV must NOT be in the toxic list; it's a legitimate runtime var."""
        assert "NODE_ENV" not in _TOXIC_NODE_ENV_VARS
        env = self._build_and_sanitize()
        assert "NODE_ENV" in env

    def test_empty_value_still_stripped(self) -> None:
        """Even empty-string toxic vars should be removed."""
        env = self._build_and_sanitize({"NODE_OPTIONS": "", "LD_PRELOAD": ""})
        assert "NODE_OPTIONS" not in env
        assert "LD_PRELOAD" not in env

    def test_whitespace_value_still_stripped(self) -> None:
        env = self._build_and_sanitize({"NODE_OPTIONS": "  ", "HTTP_PROXY": "\t"})
        assert "NODE_OPTIONS" not in env
        assert "HTTP_PROXY" not in env

    def test_all_toxic_injected_simultaneously(self) -> None:
        """All 15 toxic vars injected at once, all must be stripped."""
        all_toxic = {var: f"evil-{var}" for var in _TOXIC_NODE_ENV_VARS}
        env = self._build_and_sanitize(all_toxic)
        for var in _TOXIC_NODE_ENV_VARS:
            assert var not in env, f"{var} should be stripped even with all injected"

    def test_similar_named_vars_not_stripped(self) -> None:
        """Vars with similar names but not in the list should be preserved."""
        env = self._build_and_sanitize({
            "MY_HTTP_PROXY": "safe",
            "NODE_OPTIONS_EXTRA": "safe",
            "CUSTOM_LD_PRELOAD": "safe",
        })
        assert env["MY_HTTP_PROXY"] == "safe"
        assert env["NODE_OPTIONS_EXTRA"] == "safe"
        assert env["CUSTOM_LD_PRELOAD"] == "safe"
