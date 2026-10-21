"""
测试本地模式平台适配
"""

import tempfile

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend


class TestLocalStorageBackend:
    """测试 LocalStorageBackend"""

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield LocalStorageBackend(tmpdir)

    @pytest.mark.asyncio
    async def test_write_and_read(self, temp_storage):
        """测试写入和读取"""
        path = "test/file.txt"
        content = b"Test content"

        await temp_storage.write(path, content)
        result = await temp_storage.read(path)

        assert result == content

    @pytest.mark.asyncio
    async def test_write_and_read_text(self, temp_storage):
        """测试写入和读取文本"""
        path = "test/text.txt"
        content = "你好，世界！"

        await temp_storage.write_text(path, content)
        result = await temp_storage.read_text(path)

        assert result == content

    @pytest.mark.asyncio
    async def test_exists(self, temp_storage):
        """测试检查文件是否存在"""
        path = "test/exists.txt"

        assert await temp_storage.exists(path) is False

        await temp_storage.write(path, b"content")

        assert await temp_storage.exists(path) is True

    @pytest.mark.asyncio
    async def test_delete(self, temp_storage):
        """测试删除文件"""
        path = "test/delete.txt"

        await temp_storage.write(path, b"to delete")
        assert await temp_storage.exists(path) is True

        await temp_storage.delete(path)
        assert await temp_storage.exists(path) is False

    @pytest.mark.asyncio
    async def test_list(self, temp_storage):
        """测试列出文件"""
        await temp_storage.write("dir/file1.txt", b"1")
        await temp_storage.write("dir/file2.txt", b"2")
        await temp_storage.write("dir/subdir/file3.txt", b"3")

        files = await temp_storage.list("dir")
        assert len(files) >= 2

    @pytest.mark.asyncio
    async def test_get_url(self, temp_storage):
        """测试获取文件 URL"""
        path = "test/url.txt"
        await temp_storage.write(path, b"content")

        url = await temp_storage.get_url(path)
        assert url.startswith("file://")


class TestPlatformDetection:
    """测试平台检测"""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        from app.config.deploy_mode import get_deploy_mode

        get_deploy_mode.cache_clear()
        yield
        get_deploy_mode.cache_clear()

    def test_deploy_mode_local(self, monkeypatch):
        """Local 模式检测"""
        monkeypatch.setenv("DEPLOY_MODE", "local")

        import importlib

        import app.platform_utils

        importlib.reload(app.platform_utils)

        assert app.platform_utils.DEPLOY_MODE == "local"
        assert app.platform_utils.is_local_mode() is True

    def test_deploy_mode_tauri_compat(self, monkeypatch):
        """DEPLOY_MODE=tauri 是独立的部署模式（单用户桌面 Sidecar）"""
        monkeypatch.setenv("DEPLOY_MODE", "tauri")

        import importlib

        import app.platform_utils

        importlib.reload(app.platform_utils)

        assert app.platform_utils.DEPLOY_MODE == "tauri"
        assert app.platform_utils.is_local_mode() is True

    def test_deploy_mode_sandbox(self, monkeypatch):
        """Sandbox 模式检测"""
        monkeypatch.setenv("DEPLOY_MODE", "sandbox")

        import importlib

        import app.platform_utils

        importlib.reload(app.platform_utils)

        assert app.platform_utils.DEPLOY_MODE == "sandbox"
        assert app.platform_utils.is_local_mode() is False

    def test_deploy_mode_invalid_fallback(self, monkeypatch):
        """无效 DEPLOY_MODE 回退到 LOCAL"""
        monkeypatch.setenv("DEPLOY_MODE", "invalid_mode")

        from app.config.deploy_mode import DeployMode, get_deploy_mode

        result = get_deploy_mode()
        assert result == DeployMode.LOCAL

    def test_deploy_mode_default(self, monkeypatch):
        """未设置 DEPLOY_MODE 默认 LOCAL"""
        monkeypatch.delenv("DEPLOY_MODE", raising=False)

        from app.config.deploy_mode import DeployMode, get_deploy_mode

        result = get_deploy_mode()
        assert result == DeployMode.LOCAL

    def test_deploy_mode_case_insensitive(self, monkeypatch):
        """DEPLOY_MODE 大小写不敏感"""
        monkeypatch.setenv("DEPLOY_MODE", "SANDBOX")

        from app.config.deploy_mode import DeployMode, get_deploy_mode

        result = get_deploy_mode()
        assert result == DeployMode.SANDBOX

    def test_is_sandbox_true(self, monkeypatch):
        """is_sandbox() 在 sandbox 模式返回 True"""
        monkeypatch.setenv("DEPLOY_MODE", "sandbox")

        from app.config.deploy_mode import is_sandbox

        assert is_sandbox() is True

    def test_is_sandbox_false_for_local(self, monkeypatch):
        """is_sandbox() 在 local 模式返回 False"""
        monkeypatch.setenv("DEPLOY_MODE", "local")

        from app.config.deploy_mode import is_sandbox

        assert is_sandbox() is False

    def test_is_local_mode(self, monkeypatch):
        """is_local_mode() 在 local 模式返回 True，sandbox 返回 False"""
        from app.config.deploy_mode import get_deploy_mode, is_local_mode

        monkeypatch.setenv("DEPLOY_MODE", "local")
        get_deploy_mode.cache_clear()
        assert is_local_mode() is True

        monkeypatch.setenv("DEPLOY_MODE", "sandbox")
        get_deploy_mode.cache_clear()
        assert is_local_mode() is False
