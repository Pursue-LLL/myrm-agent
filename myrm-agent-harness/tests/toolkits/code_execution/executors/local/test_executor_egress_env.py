"""A host-provided egress proxy is part of the environment a bash shell starts with."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor

_PROXY_KEYS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy")
_CA_KEYS = ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE", "NODE_EXTRA_CA_CERTS")


@pytest.fixture
def executor() -> LocalExecutor:
    return LocalExecutor(config=ExecutionConfig(), workspace_path="/tmp")


def test_the_shell_is_pointed_at_the_host_egress_proxy(
    executor: LocalExecutor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MYRM_EGRESS_PROXY_URL", "http://127.0.0.1:18080")
    monkeypatch.setenv("MYRM_EGRESS_CA_BUNDLE", "/etc/myrm/egress-ca.pem")

    env = executor._build_bash_env(None)

    assert {env[key] for key in _PROXY_KEYS} == {"http://127.0.0.1:18080"}
    assert env["NODE_USE_ENV_PROXY"] == "1"
    assert "127.0.0.1" in env["NO_PROXY"]
    assert {env[key] for key in _CA_KEYS} == {"/etc/myrm/egress-ca.pem"}


def test_without_a_host_egress_proxy_the_shell_env_has_no_proxy_settings(
    executor: LocalExecutor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MYRM_EGRESS_PROXY_URL", raising=False)
    monkeypatch.delenv("MYRM_EGRESS_CA_BUNDLE", raising=False)

    env = executor._build_bash_env(None)

    assert "NODE_USE_ENV_PROXY" not in env
    assert not any(key in env for key in ("MYRM_EGRESS_PROXY_URL", "MYRM_EGRESS_CA_BUNDLE"))
