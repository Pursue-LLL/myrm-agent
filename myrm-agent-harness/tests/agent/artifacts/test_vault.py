"""Unit tests for ArtifactVault."""

import sys
from pathlib import Path

import pytest

from myrm_agent_harness.agent.artifacts.vault import VAULT_PREFIX, ArtifactVault


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    """Provide a temporary workspace directory."""
    return tmp_path


@pytest.fixture
def vault(workspace_dir: Path) -> ArtifactVault:
    """Provide an ArtifactVault instance."""
    return ArtifactVault(str(workspace_dir))


class TestArtifactVault:
    """Tests for ArtifactVault."""

    def test_init(self, workspace_dir: Path, vault: ArtifactVault):
        """Opening a vault computes its layout without touching the disk."""
        assert vault.workspace_root == workspace_dir
        assert not vault.vault_dir.exists()

    def test_reading_an_empty_vault_leaves_the_workspace_untouched(self, vault: ArtifactVault):
        assert vault.list_objects() == []
        assert vault.get_meta(f"{VAULT_PREFIX}missing") is None
        with pytest.raises(FileNotFoundError):
            vault.get(f"{VAULT_PREFIX}missing")
        assert not vault.vault_dir.exists()

    def test_first_write_creates_the_directories(self, vault: ArtifactVault):
        vault.put("x", "x.txt")

        assert vault.objects_dir.is_dir()
        assert vault.meta_dir.is_dir()

    def test_get_object_path(self, vault: ArtifactVault):
        """Test getting object path."""
        obj_id = "test-id"
        path = vault.get_object_path(obj_id)
        assert path == vault.objects_dir / obj_id

    def test_put_string(self, vault: ArtifactVault):
        """Test putting string content."""
        content = "Hello, World!"
        uri = vault.put(content, "test.txt")

        assert uri.startswith(VAULT_PREFIX)
        obj_id = uri[len(VAULT_PREFIX) :]

        # Check physical file
        obj_path = vault.get_object_path(obj_id)
        assert obj_path.exists()
        assert obj_path.read_text() == content

        # Check metadata
        meta = vault.get_meta(uri)
        assert meta is not None
        assert meta.filename == "test.txt"
        assert meta.content_type == "text/plain"
        assert meta.size_bytes == len(content.encode("utf-8"))
        assert meta.sha256_hash != ""

    def test_put_bytes(self, vault: ArtifactVault):
        """Test putting bytes content."""
        content = b"Binary\x00Data"
        uri = vault.put(content, "data.bin", content_type="application/octet-stream")

        obj_id = uri[len(VAULT_PREFIX) :]
        obj_path = vault.get_object_path(obj_id)
        assert obj_path.read_bytes() == content

        meta = vault.get_meta(uri)
        assert meta is not None
        assert meta.content_type == "application/octet-stream"
        assert meta.size_bytes == len(content)

    def test_put_mime_sniffing(self, vault: ArtifactVault):
        """Test MIME type sniffing in put()."""
        uri = vault.put("test", "report.pdf")
        meta = vault.get_meta(uri)
        assert meta is not None
        assert meta.content_type == "application/pdf"

    def test_put_file(self, workspace_dir: Path, vault: ArtifactVault):
        """Test putting a file from disk."""
        source_file = workspace_dir / "source.txt"
        content = b"File content"
        source_file.write_bytes(content)

        uri = vault.put_file(source_file, "source.txt")

        obj_id = uri[len(VAULT_PREFIX) :]
        obj_path = vault.get_object_path(obj_id)
        assert obj_path.exists()
        assert obj_path.read_bytes() == content

        meta = vault.get_meta(uri)
        assert meta is not None
        assert meta.filename == "source.txt"
        assert meta.content_type == "text/plain"
        assert meta.size_bytes == len(content)

    def test_put_file_not_found(self, vault: ArtifactVault):
        """Test put_file with non-existent file."""
        with pytest.raises(FileNotFoundError):
            vault.put_file("nonexistent.txt", "test.txt")

    def test_get(self, vault: ArtifactVault):
        """Test getting content."""
        content = b"Test content"
        uri = vault.put(content, "test.bin")

        retrieved = vault.get(uri)
        assert retrieved == content

    def test_get_invalid_uri(self, vault: ArtifactVault):
        """Test get with invalid URI."""
        with pytest.raises(ValueError):
            vault.get("invalid://uri")

    def test_get_not_found(self, vault: ArtifactVault):
        """Test get with non-existent object."""
        with pytest.raises(FileNotFoundError):
            vault.get(f"{VAULT_PREFIX}nonexistent")

    def test_get_meta_invalid_uri(self, vault: ArtifactVault):
        """Test get_meta with invalid URI."""
        assert vault.get_meta("invalid://uri") is None

    def test_get_meta_not_found(self, vault: ArtifactVault):
        """Test get_meta with non-existent object."""
        assert vault.get_meta(f"{VAULT_PREFIX}nonexistent") is None

    def test_list_objects(self, vault: ArtifactVault):
        """Test listing objects."""
        assert len(vault.list_objects()) == 0

        vault.put("1", "1.txt")
        vault.put("2", "2.txt")

        objects = vault.list_objects()
        assert len(objects) == 2
        # Should be sorted by created_at descending
        assert objects[0].filename == "2.txt"
        assert objects[1].filename == "1.txt"

    def test_list_objects_corrupted_meta(self, vault: ArtifactVault):
        """Test listing objects with corrupted metadata file."""
        uri = vault.put("test", "test.txt")
        obj_id = uri[len(VAULT_PREFIX) :]

        # Corrupt the metadata file
        meta_path = vault._get_meta_path(obj_id)
        meta_path.write_text("invalid json")

        # Should skip corrupted file and return empty list
        objects = vault.list_objects()
        assert len(objects) == 0


class TestVaultPlatformIndependence:
    """The vault writes on platforms that ship no ``fcntl`` (Windows)."""

    @pytest.fixture(autouse=True)
    def _no_fcntl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "fcntl", None)

    def test_put_without_fcntl(self, vault: ArtifactVault):
        uri = vault.put("payload", "p.txt")

        assert vault.get(uri) == b"payload"

    def test_put_file_without_fcntl(self, vault: ArtifactVault, tmp_path: Path):
        src = tmp_path / "src.bin"
        src.write_bytes(b"\x00\x01" * 10)

        uri = vault.put_file(src, "src.bin")

        assert vault.get(uri) == src.read_bytes()
