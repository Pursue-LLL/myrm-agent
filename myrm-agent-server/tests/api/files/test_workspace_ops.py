"""Tests for workspace file write-operations API endpoints.

Covers:
- POST /browse/upload — file upload to workspace
- POST /browse/mkdir  — create directory
- POST /browse/rename — rename file/directory
- POST /browse/move   — move file/directory
- DELETE /browse/delete — delete file/directory
- PUT /browse/content — save file content (online edit)
- Security: boundary, dangerous path, protected names, size limits
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def workspace_dir(tmp_path):
    """Create a temporary workspace with known structure."""
    (tmp_path / "readme.md").write_text("# Hello")
    (tmp_path / "config.yaml").write_text("key: value")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "app.ts").write_text("export default {};")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]")
    return str(tmp_path)


# -----------------------------------------------------------------------
# POST /browse/mkdir
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_mkdir_creates_directory(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/mkdir",
        json={"workspace": workspace_dir, "path": "new_folder"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "new_folder"
    assert os.path.isdir(os.path.join(workspace_dir, "new_folder"))


@pytest.mark.anyio
async def test_mkdir_rejects_existing_path(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/mkdir",
        json={"workspace": workspace_dir, "path": "src"},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_mkdir_rejects_invalid_name(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/mkdir",
        json={"workspace": workspace_dir, "path": ".."},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_mkdir_rejects_dangerous_workspace(client: AsyncClient):
    resp = await client.post(
        "/api/v1/files/browse/mkdir",
        json={"workspace": "/etc", "path": "test_dir"},
    )
    assert resp.status_code in (400, 422)


# -----------------------------------------------------------------------
# POST /browse/rename
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_rename_file(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/rename",
        json={
            "workspace": workspace_dir,
            "path": "readme.md",
            "new_name": "intro.md",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["old_name"] == "readme.md"
    assert data["new_name"] == "intro.md"
    assert os.path.exists(os.path.join(workspace_dir, "intro.md"))
    assert not os.path.exists(os.path.join(workspace_dir, "readme.md"))


@pytest.mark.anyio
async def test_rename_rejects_nonexistent(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/rename",
        json={
            "workspace": workspace_dir,
            "path": "nonexistent.txt",
            "new_name": "new.txt",
        },
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_rename_rejects_duplicate_name(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/rename",
        json={
            "workspace": workspace_dir,
            "path": "readme.md",
            "new_name": "config.yaml",
        },
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_rename_rejects_protected_git(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/rename",
        json={
            "workspace": workspace_dir,
            "path": ".git",
            "new_name": "git_backup",
        },
    )
    assert resp.status_code in (400, 422)


# -----------------------------------------------------------------------
# POST /browse/move
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_move_file_to_subdir(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/move",
        json={
            "workspace": workspace_dir,
            "source": "config.yaml",
            "target_dir": "src",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "config.yaml"
    assert os.path.exists(os.path.join(workspace_dir, "src", "config.yaml"))
    assert not os.path.exists(os.path.join(workspace_dir, "config.yaml"))


@pytest.mark.anyio
async def test_move_rejects_nonexistent_source(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/move",
        json={
            "workspace": workspace_dir,
            "source": "nope.txt",
            "target_dir": "src",
        },
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_move_rejects_nonexistent_target(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/move",
        json={
            "workspace": workspace_dir,
            "source": "readme.md",
            "target_dir": "nonexistent_dir",
        },
    )
    assert resp.status_code in (400, 422)


# -----------------------------------------------------------------------
# DELETE /browse/delete
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_file(client: AsyncClient, workspace_dir: str):
    resp = await client.request(
        "DELETE",
        "/api/v1/files/browse/delete",
        params={"workspace": workspace_dir, "path": "readme.md"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deleted"] == "readme.md"
    assert data["type"] == "file"
    assert not os.path.exists(os.path.join(workspace_dir, "readme.md"))


@pytest.mark.anyio
async def test_delete_directory(client: AsyncClient, workspace_dir: str):
    new_dir = os.path.join(workspace_dir, "to_delete")
    os.mkdir(new_dir)
    (tmp := os.path.join(new_dir, "file.txt"))
    with open(tmp, "w") as f:
        f.write("temp")

    resp = await client.request(
        "DELETE",
        "/api/v1/files/browse/delete",
        params={"workspace": workspace_dir, "path": "to_delete"},
    )
    assert resp.status_code == 200
    assert not os.path.exists(new_dir)


@pytest.mark.anyio
async def test_delete_rejects_workspace_root(client: AsyncClient, workspace_dir: str):
    resp = await client.request(
        "DELETE",
        "/api/v1/files/browse/delete",
        params={"workspace": workspace_dir, "path": workspace_dir},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_delete_rejects_protected_git(client: AsyncClient, workspace_dir: str):
    resp = await client.request(
        "DELETE",
        "/api/v1/files/browse/delete",
        params={"workspace": workspace_dir, "path": ".git"},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_delete_rejects_nonexistent(client: AsyncClient, workspace_dir: str):
    resp = await client.request(
        "DELETE",
        "/api/v1/files/browse/delete",
        params={"workspace": workspace_dir, "path": "nope.txt"},
    )
    assert resp.status_code in (400, 422)


# -----------------------------------------------------------------------
# PUT /browse/content — save file content
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_save_content_creates_file(client: AsyncClient, workspace_dir: str):
    resp = await client.put(
        "/api/v1/files/browse/content",
        json={
            "workspace": workspace_dir,
            "path": "new_file.txt",
            "content": "hello world",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "new_file.txt"
    assert data["size"] == 11
    with open(os.path.join(workspace_dir, "new_file.txt")) as f:
        assert f.read() == "hello world"


@pytest.mark.anyio
async def test_save_content_overwrites_existing(client: AsyncClient, workspace_dir: str):
    resp = await client.put(
        "/api/v1/files/browse/content",
        json={
            "workspace": workspace_dir,
            "path": "readme.md",
            "content": "# Updated",
        },
    )
    assert resp.status_code == 200
    with open(os.path.join(workspace_dir, "readme.md")) as f:
        assert f.read() == "# Updated"


@pytest.mark.anyio
async def test_save_content_rejects_directory(client: AsyncClient, workspace_dir: str):
    resp = await client.put(
        "/api/v1/files/browse/content",
        json={
            "workspace": workspace_dir,
            "path": "src",
            "content": "data",
        },
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_save_content_rejects_outside_workspace(client: AsyncClient, workspace_dir: str):
    resp = await client.put(
        "/api/v1/files/browse/content",
        json={
            "workspace": workspace_dir,
            "path": "/etc/passwd",
            "content": "hacked",
        },
    )
    assert resp.status_code in (400, 422)


# -----------------------------------------------------------------------
# POST /browse/upload
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_upload_single_file(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/upload",
        params={"workspace": workspace_dir},
        files=[("files", ("test.txt", b"file content", "text/plain"))],
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["uploaded_count"] == 1
    assert os.path.exists(os.path.join(workspace_dir, "test.txt"))


@pytest.mark.anyio
async def test_upload_to_subdir(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/upload",
        params={"workspace": workspace_dir, "target_dir": "src"},
        files=[("files", ("upload.js", b"const x = 1;", "text/javascript"))],
    )
    assert resp.status_code == 200
    assert os.path.exists(os.path.join(workspace_dir, "src", "upload.js"))


@pytest.mark.anyio
async def test_upload_dedup_filename(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/upload",
        params={"workspace": workspace_dir},
        files=[("files", ("readme.md", b"duplicate", "text/plain"))],
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["files"][0]["name"] == "readme (1).md"


@pytest.mark.anyio
async def test_upload_rejects_empty(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/upload",
        params={"workspace": workspace_dir},
        files=[],
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_upload_rejects_nonexistent_target_dir(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/upload",
        params={"workspace": workspace_dir, "target_dir": "nonexistent"},
        files=[("files", ("test.txt", b"data", "text/plain"))],
    )
    assert resp.status_code in (400, 422)


# -----------------------------------------------------------------------
# Security: path traversal
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_mkdir_path_traversal_rejected(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/mkdir",
        json={"workspace": workspace_dir, "path": "../../../tmp/evil"},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_save_content_path_traversal_rejected(client: AsyncClient, workspace_dir: str):
    resp = await client.put(
        "/api/v1/files/browse/content",
        json={
            "workspace": workspace_dir,
            "path": "../../../tmp/evil.txt",
            "content": "hacked",
        },
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_rename_slash_in_name_rejected(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/rename",
        json={
            "workspace": workspace_dir,
            "path": "readme.md",
            "new_name": "sub/evil.md",
        },
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_rename_dot_dot_rejected(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/rename",
        json={"workspace": workspace_dir, "path": "readme.md", "new_name": ".."},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_move_path_traversal_rejected(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/move",
        json={
            "workspace": workspace_dir,
            "source": "readme.md",
            "target_dir": "../../../tmp",
        },
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_move_duplicate_in_target_rejected(client: AsyncClient, workspace_dir: str):
    (tmp := os.path.join(workspace_dir, "src", "readme.md"))
    with open(tmp, "w") as f:
        f.write("dup")

    resp = await client.post(
        "/api/v1/files/browse/move",
        json={
            "workspace": workspace_dir,
            "source": "readme.md",
            "target_dir": "src",
        },
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_delete_path_traversal_rejected(client: AsyncClient, workspace_dir: str):
    resp = await client.request(
        "DELETE",
        "/api/v1/files/browse/delete",
        params={"workspace": workspace_dir, "path": "../../../tmp/important"},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_upload_path_traversal_target_dir_rejected(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/upload",
        params={"workspace": workspace_dir, "target_dir": "../../../tmp"},
        files=[("files", ("evil.txt", b"data", "text/plain"))],
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_save_content_parent_dir_missing_rejected(client: AsyncClient, workspace_dir: str):
    resp = await client.put(
        "/api/v1/files/browse/content",
        json={
            "workspace": workspace_dir,
            "path": "nonexistent_dir/file.txt",
            "content": "data",
        },
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_upload_multiple_files(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/browse/upload",
        params={"workspace": workspace_dir},
        files=[
            ("files", ("a.txt", b"aaa", "text/plain")),
            ("files", ("b.txt", b"bbb", "text/plain")),
            ("files", ("c.txt", b"ccc", "text/plain")),
        ],
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["uploaded_count"] == 3
    for name in ("a.txt", "b.txt", "c.txt"):
        assert os.path.exists(os.path.join(workspace_dir, name))
