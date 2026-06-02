"""
测试本地模式平台适配
"""

import tempfile

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.platform_utils.local.file_service import LocalFileService


class TestLocalFileService:
    """测试 LocalFileService"""

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorageBackend(tmpdir)
            yield storage

    @pytest.fixture
    def file_service(self, temp_storage):
        """创建文件服务"""
        return LocalFileService(storage=temp_storage)

    @pytest.mark.asyncio
    async def test_upload_file(self, file_service):
        """测试上传文件"""
        content = b"Hello, World!"
        file = await file_service.upload_file(
            filename="test.txt",
            content=content,
        )

        assert file.id.startswith("file_")
        assert file.filename == "test.txt"
        assert file.size == len(content)
        assert "uploads/" in file.storage_path

    @pytest.mark.asyncio
    async def test_get_file(self, file_service):
        """测试获取文件信息"""
        content = b"Test content"
        uploaded = await file_service.upload_file(
            filename="data.csv",
            content=content,
        )

        file = await file_service.get_file(uploaded.id)
        assert file is not None
        assert file.id == uploaded.id
        assert file.filename == "data.csv"

    @pytest.mark.asyncio
    async def test_get_file_not_found(self, file_service):
        """测试获取不存在的文件"""
        file = await file_service.get_file("nonexistent_id")
        assert file is None

    @pytest.mark.asyncio
    async def test_get_file_wrong_user(self, file_service):
        """测试获取不存在的文件返回 None"""
        file = await file_service.get_file("nonexistent_file_id_xyz")
        assert file is None

    @pytest.mark.asyncio
    async def test_get_content(self, file_service):
        """测试获取文件内容"""
        original_content = b"Binary data here"
        uploaded = await file_service.upload_file(
            filename="binary.bin",
            content=original_content,
        )

        content = await file_service.get_content(uploaded.id)
        assert content == original_content

    @pytest.mark.asyncio
    async def test_get_content_not_found(self, file_service):
        """测试获取不存在文件的内容"""
        with pytest.raises(FileNotFoundError):
            await file_service.get_content("nonexistent_id")

    @pytest.mark.asyncio
    async def test_delete_file(self, file_service):
        """测试删除文件"""
        content = b"To be deleted"
        uploaded = await file_service.upload_file(
            filename="delete_me.txt",
            content=content,
        )

        result = await file_service.delete_file(uploaded.id)
        assert result is True

        file = await file_service.get_file(uploaded.id)
        assert file is None

    @pytest.mark.asyncio
    async def test_delete_file_wrong_user(self, file_service):
        """测试删除不存在的文件返回 False"""
        result = await file_service.delete_file("nonexistent_file_id_xyz")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_files(self, file_service):
        """测试列出文件"""
        for i in range(3):
            await file_service.upload_file(
                filename=f"file_{i}.txt",
                content=f"Content {i}".encode(),
            )

        files = await file_service.list_files()
        assert len(files) == 3

    @pytest.mark.asyncio
    async def test_save_file_requires_sandbox_path(self, file_service):
        """测试 save_file 需要 sandbox_path"""
        with pytest.raises(ValueError) as excinfo:
            await file_service.save_file(
                chat_id="chat_456",
                filename="test.txt",
                content=b"Should fail",
            )

        assert "sandbox_path" in str(excinfo.value)


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
