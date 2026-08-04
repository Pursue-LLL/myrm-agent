"""Unit tests for tests/support/test_secrets.py."""

from tests.support.test_secrets import (
    TestSecrets,
    apply_test_secrets_to_environ,
    clear_test_secrets_cache,
    load_test_secrets,
    resolve_test_env,
)


def test_load_test_secrets_returns_mapping() -> None:
    secrets = load_test_secrets()
    assert isinstance(secrets, TestSecrets)
    assert isinstance(secrets.raw, dict)


def test_has_basic_credentials_false_when_empty() -> None:
    secrets = TestSecrets(raw={})
    assert secrets.has_basic_credentials is False


def test_resolve_test_env_prefers_environ_over_secrets(monkeypatch) -> None:
    monkeypatch.setenv("BASIC_MODEL", "from-env")
    assert resolve_test_env("BASIC_MODEL") == "from-env"


def test_resolve_test_env_falls_back_to_secrets(monkeypatch) -> None:
    monkeypatch.delenv("BASIC_MODEL", raising=False)
    file_value = load_test_secrets().get("BASIC_MODEL")
    if file_value:
        assert resolve_test_env("BASIC_MODEL") == file_value


def test_apply_test_secrets_to_environ(monkeypatch) -> None:
    monkeypatch.delenv("BASIC_API_KEY", raising=False)
    apply_test_secrets_to_environ(TestSecrets(raw={"BASIC_API_KEY": "secret"}))
    assert resolve_test_env("BASIC_API_KEY") == "secret"
    clear_test_secrets_cache()
