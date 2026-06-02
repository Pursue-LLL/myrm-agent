"""deploy_mode 部署模式测试

覆盖场景:
- DeployMode 枚举值
- get_deploy_mode() 正常/无效值 fallback
- is_local_mode / is_sandbox 判定
- is_webui_mode / is_webui_remote_mode 判定
- get_deploy_mode lru_cache 行为
"""

from app.config.deploy_mode import (
    DatabaseMode,
    DeployMode,
    ModelSource,
    QdrantMode,
    StorageMode,
    get_database_mode,
    get_deploy_mode,
    get_embedding_mode,
    get_qdrant_mode,
    get_reranker_mode,
    get_storage_mode,
    is_local_mode,
    is_sandbox,
    is_webui_mode,
    is_webui_remote_mode,
)


def _with_env(monkeypatch, **env: str):
    """设置环境变量并清除 lru_cache"""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_deploy_mode.cache_clear()


def _clear_env(monkeypatch, *keys: str):
    """移除环境变量并清除 lru_cache"""
    for k in keys:
        monkeypatch.delenv(k, raising=False)
    get_deploy_mode.cache_clear()


class TestDeployMode:
    def test_local_mode(self, monkeypatch) -> None:
        _with_env(monkeypatch, DEPLOY_MODE="local")
        assert get_deploy_mode() == DeployMode.LOCAL

    def test_sandbox_mode(self, monkeypatch) -> None:
        _with_env(monkeypatch, DEPLOY_MODE="sandbox")
        assert get_deploy_mode() == DeployMode.SANDBOX

    def test_invalid_mode_fallback(self, monkeypatch) -> None:
        _with_env(monkeypatch, DEPLOY_MODE="unknown_mode")
        assert get_deploy_mode() == DeployMode.LOCAL

    def test_empty_mode_fallback(self, monkeypatch) -> None:
        _clear_env(monkeypatch, "DEPLOY_MODE")
        assert get_deploy_mode() == DeployMode.LOCAL

    def test_case_insensitive(self, monkeypatch) -> None:
        _with_env(monkeypatch, DEPLOY_MODE="SANDBOX")
        assert get_deploy_mode() == DeployMode.SANDBOX


class TestModePredicates:
    def test_is_local_mode_true(self, monkeypatch) -> None:
        _with_env(monkeypatch, DEPLOY_MODE="local")
        assert is_local_mode() is True

    def test_is_local_mode_false(self, monkeypatch) -> None:
        _with_env(monkeypatch, DEPLOY_MODE="sandbox")
        assert is_local_mode() is False

    def test_is_sandbox_true(self, monkeypatch) -> None:
        _with_env(monkeypatch, DEPLOY_MODE="sandbox")
        assert is_sandbox() is True

    def test_is_sandbox_false(self, monkeypatch) -> None:
        _with_env(monkeypatch, DEPLOY_MODE="local")
        assert is_sandbox() is False


class TestWebUIMode:
    def test_webui_mode_false_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv("WEBUI_MODE", raising=False)
        assert is_webui_mode() is False

    def test_webui_mode_true(self, monkeypatch) -> None:
        monkeypatch.setenv("WEBUI_MODE", "true")
        assert is_webui_mode() is True

    def test_webui_remote_mode_false_without_webui(self, monkeypatch) -> None:
        monkeypatch.delenv("WEBUI_MODE", raising=False)
        monkeypatch.setenv("WEBUI_REMOTE_MODE", "true")
        assert is_webui_remote_mode() is False

    def test_webui_remote_mode_true(self, monkeypatch) -> None:
        monkeypatch.setenv("WEBUI_MODE", "true")
        monkeypatch.setenv("WEBUI_REMOTE_MODE", "true")
        assert is_webui_remote_mode() is True

    def test_webui_remote_mode_false_when_webui_only(self, monkeypatch) -> None:
        monkeypatch.setenv("WEBUI_MODE", "true")
        monkeypatch.delenv("WEBUI_REMOTE_MODE", raising=False)
        assert is_webui_remote_mode() is False


class TestStaticModes:
    def test_database_mode_always_sqlite(self) -> None:
        assert get_database_mode() == DatabaseMode.SQLITE

    def test_qdrant_mode_always_embedded(self) -> None:
        assert get_qdrant_mode() == QdrantMode.EMBEDDED

    def test_storage_mode_default_local(self, monkeypatch) -> None:
        monkeypatch.delenv("STORAGE_MODE", raising=False)
        assert get_storage_mode() == StorageMode.LOCAL

    def test_embedding_mode_always_custom(self) -> None:
        assert get_embedding_mode() == ModelSource.CUSTOM

    def test_reranker_mode_always_custom(self) -> None:
        assert get_reranker_mode() == ModelSource.CUSTOM
