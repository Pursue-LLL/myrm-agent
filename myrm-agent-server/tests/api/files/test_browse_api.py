"""Tests for directory/file browse API endpoints.

Covers:
- GET /browse — directory listing for workspace picker
- GET /browse/files — recursive file tree for workspace browser
- GET /browse/content — file content preview/download
"""

import os
import uuid

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
    (tmp_path / "main.py").write_text("print('hello')")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "app.ts").write_text("export default {};")
    (tmp_path / ".hidden_file").write_text("secret")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.json").write_text("{}")
    (tmp_path / ".env").write_text("SECRET=xyz")
    return str(tmp_path)


# -----------------------------------------------------------------------
# GET /browse — directory-only listing
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_home_directory(client: AsyncClient):
    """Browse home directory returns valid response."""
    resp = await client.get("/api/v1/files/browse", params={"path": "~"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert "current" in data
    assert "entries" in data
    assert isinstance(data["entries"], list)
    assert len(data["entries"]) > 0
    for entry in data["entries"]:
        assert entry["is_dir"] is True
        assert not entry["name"].startswith(".")


@pytest.mark.anyio
async def test_browse_dangerous_path_rejected(client: AsyncClient):
    """Browsing /etc should be rejected."""
    resp = await client.get("/api/v1/files/browse", params={"path": "/etc"})
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_nonexistent_path(client: AsyncClient):
    """Browsing non-existent path should fail."""
    resp = await client.get("/api/v1/files/browse", params={"path": "/nonexistent_xyz_abc_123"})
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_returns_parent(client: AsyncClient):
    """Browse non-root dir should include parent."""
    home = os.path.expanduser("~")
    resp = await client.get("/api/v1/files/browse", params={"path": home})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["parent"] is not None


@pytest.mark.anyio
async def test_browse_hides_hidden_dirs(client: AsyncClient):
    """Hidden directories (starting with .) should not appear."""
    resp = await client.get("/api/v1/files/browse", params={"path": "~"})
    assert resp.status_code == 200
    entries = resp.json()["data"]["entries"]
    for entry in entries:
        assert not entry["name"].startswith(".")


# -----------------------------------------------------------------------
# GET /browse/files — recursive file tree
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_files_returns_tree(client: AsyncClient, workspace_dir: str):
    """browse/files returns file tree with correct structure."""
    resp = await client.get("/api/v1/files/browse/files", params={"path": workspace_dir, "depth": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["root"] == os.path.realpath(workspace_dir)
    assert isinstance(data["entries"], list)
    assert data["truncated"] is False

    names = {e["name"] for e in data["entries"]}
    assert "readme.md" in names
    assert "main.py" in names
    assert "src" in names


@pytest.mark.anyio
async def test_browse_files_filters_hidden(client: AsyncClient, workspace_dir: str):
    """Hidden files/dirs should not appear in file tree."""
    resp = await client.get("/api/v1/files/browse/files", params={"path": workspace_dir, "depth": 2})
    assert resp.status_code == 200
    entries = resp.json()["data"]["entries"]
    all_names = _collect_names(entries)
    assert ".hidden_file" not in all_names
    assert ".git" not in all_names


@pytest.mark.anyio
async def test_browse_files_filters_ignored_dirs(client: AsyncClient, workspace_dir: str):
    """node_modules and other ignored dirs should not appear."""
    resp = await client.get("/api/v1/files/browse/files", params={"path": workspace_dir, "depth": 2})
    assert resp.status_code == 200
    entries = resp.json()["data"]["entries"]
    all_names = _collect_names(entries)
    assert "node_modules" not in all_names


@pytest.mark.anyio
async def test_browse_files_includes_metadata(client: AsyncClient, workspace_dir: str):
    """File entries should include size and mtime metadata."""
    resp = await client.get("/api/v1/files/browse/files", params={"path": workspace_dir, "depth": 1})
    assert resp.status_code == 200
    entries = resp.json()["data"]["entries"]
    file_entries = [e for e in entries if e["type"] == "file"]
    assert len(file_entries) > 0
    for fe in file_entries:
        assert fe["size"] is not None
        assert fe["size"] >= 0
        assert fe["mtime"] is not None


@pytest.mark.anyio
async def test_browse_files_depth_limit(client: AsyncClient, workspace_dir: str):
    """Depth=1 should not recurse into subdirectories."""
    resp = await client.get("/api/v1/files/browse/files", params={"path": workspace_dir, "depth": 1})
    assert resp.status_code == 200
    entries = resp.json()["data"]["entries"]
    src_entry = next((e for e in entries if e["name"] == "src"), None)
    assert src_entry is not None
    assert src_entry["children"] is None


@pytest.mark.anyio
async def test_browse_files_depth_2_has_children(client: AsyncClient, workspace_dir: str):
    """Depth=2 should recurse and show children."""
    resp = await client.get("/api/v1/files/browse/files", params={"path": workspace_dir, "depth": 2})
    assert resp.status_code == 200
    entries = resp.json()["data"]["entries"]
    src_entry = next((e for e in entries if e["name"] == "src"), None)
    assert src_entry is not None
    assert src_entry["children"] is not None
    child_names = {c["name"] for c in src_entry["children"]}
    assert "app.ts" in child_names


@pytest.mark.anyio
async def test_browse_files_rejects_dangerous_path(client: AsyncClient):
    """Dangerous paths should be rejected."""
    resp = await client.get("/api/v1/files/browse/files", params={"path": "/etc"})
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_files_rejects_nonexistent(client: AsyncClient):
    """Non-existent path should fail."""
    resp = await client.get("/api/v1/files/browse/files", params={"path": "/nonexistent_path_xyz"})
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_files_filters_sensitive(client: AsyncClient, workspace_dir: str):
    """Sensitive files like .env should be filtered out."""
    resp = await client.get("/api/v1/files/browse/files", params={"path": workspace_dir, "depth": 1})
    assert resp.status_code == 200
    entries = resp.json()["data"]["entries"]
    all_names = _collect_names(entries)
    assert ".env" not in all_names


# -----------------------------------------------------------------------
# GET /browse/content — file content read
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_content_preview(client: AsyncClient, workspace_dir: str):
    """Reading a text file for preview returns correct content."""
    file_path = os.path.join(workspace_dir, "readme.md")
    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": file_path, "workspace": workspace_dir},
    )
    assert resp.status_code == 200
    assert resp.text == "# Hello"
    assert "inline" in resp.headers.get("content-disposition", "")


@pytest.mark.anyio
async def test_browse_content_via_chat_id_relative_path(
    client: AsyncClient, workspace_dir: str
) -> None:
    """chat_id resolves workspace root; relative path joins inside boundary."""
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    chat_id = f"browse-chat-{uuid.uuid4().hex[:8]}"
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title="browse probe",
                action_mode="agent",
                source="web",
                workspace_dir=workspace_dir,
            )
        )
        await db.commit()

    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": "readme.md", "chat_id": chat_id},
    )
    assert resp.status_code == 200
    assert resp.text == "# Hello"


@pytest.mark.anyio
async def test_browse_content_via_chat_id_absolute_path(
    client: AsyncClient, workspace_dir: str
) -> None:
    """chat_id plus absolute path within workspace returns content."""
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    chat_id = f"browse-chat-abs-{uuid.uuid4().hex[:8]}"
    file_path = os.path.join(workspace_dir, "readme.md")
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title="browse probe abs",
                action_mode="agent",
                source="web",
                workspace_dir=workspace_dir,
            )
        )
        await db.commit()

    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": file_path, "chat_id": chat_id},
    )
    assert resp.status_code == 200
    assert resp.text == "# Hello"


@pytest.mark.anyio
async def test_browse_content_requires_workspace_or_chat_id(
    client: AsyncClient, workspace_dir: str,
) -> None:
    """Boundary root is mandatory: omitting both workspace and chat_id must fail."""
    file_path = os.path.join(workspace_dir, "readme.md")
    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": file_path},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_content_download(client: AsyncClient, workspace_dir: str):
    """Download mode sets attachment disposition."""
    file_path = os.path.join(workspace_dir, "main.py")
    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": file_path, "workspace": workspace_dir, "download": "true"},
    )
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert resp.text == "print('hello')"


@pytest.mark.anyio
async def test_browse_content_outside_workspace_rejected(client: AsyncClient, workspace_dir: str):
    """File outside workspace boundary should be rejected."""
    outside_file = os.path.expanduser("~/.bashrc")
    if not os.path.exists(outside_file):
        pytest.skip("~/.bashrc not available")
    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": outside_file, "workspace": workspace_dir},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_content_sensitive_file_rejected(client: AsyncClient, workspace_dir: str):
    """Sensitive files like .env should be rejected."""
    env_path = os.path.join(workspace_dir, ".env")
    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": env_path, "workspace": workspace_dir},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_content_nonexistent_file(client: AsyncClient, workspace_dir: str):
    """Non-existent file should fail."""
    fake_path = os.path.join(workspace_dir, "does_not_exist.txt")
    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": fake_path, "workspace": workspace_dir},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_content_dangerous_path_rejected(client: AsyncClient, workspace_dir: str):
    """Dangerous system paths should be rejected."""
    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": "/etc/passwd", "workspace": "/etc"},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_content_file_too_large(client: AsyncClient, workspace_dir: str, tmp_path):
    """Files exceeding 1MB should be truncated."""
    large_file = os.path.join(workspace_dir, "large.txt")
    with open(large_file, "wb") as f:
        f.write(b"x" * (1024 * 1024 + 1))
    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": large_file, "workspace": workspace_dir},
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Truncated") == "true"
    assert len(resp.content) == 1024 * 1024


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_files_empty_directory(client: AsyncClient, tmp_path):
    """Empty directory should return empty entries list."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    resp = await client.get("/api/v1/files/browse/files", params={"path": str(empty_dir), "depth": 1})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["entries"] == []
    assert data["truncated"] is False


@pytest.mark.anyio
async def test_browse_files_path_traversal_attack(client: AsyncClient, workspace_dir: str):
    """Path traversal via .. should be resolved and blocked if outside workspace."""
    traversal_path = workspace_dir + "/src/../../../../../../etc"
    resp = await client.get("/api/v1/files/browse/files", params={"path": traversal_path})
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_content_directory_rejected(client: AsyncClient, workspace_dir: str):
    """Attempting to read a directory as content should fail."""
    sub_dir = os.path.join(workspace_dir, "src")
    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": sub_dir, "workspace": workspace_dir},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_content_path_traversal_rejected(client: AsyncClient, workspace_dir: str):
    """Path traversal in content endpoint should be rejected."""
    traversal_path = workspace_dir + "/src/../../etc/passwd"
    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": traversal_path, "workspace": workspace_dir},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_files_sorts_dirs_first(client: AsyncClient, workspace_dir: str):
    """Directories should appear before files in the listing."""
    resp = await client.get("/api/v1/files/browse/files", params={"path": workspace_dir, "depth": 1})
    assert resp.status_code == 200
    entries = resp.json()["data"]["entries"]
    types = [e["type"] for e in entries]
    dir_indices = [i for i, t in enumerate(types) if t == "directory"]
    file_indices = [i for i, t in enumerate(types) if t == "file"]
    if dir_indices and file_indices:
        assert max(dir_indices) < min(file_indices)


@pytest.mark.anyio
async def test_browse_content_correct_content_type(client: AsyncClient, workspace_dir: str):
    """Content endpoint should return appropriate content-type for known file types."""
    py_path = os.path.join(workspace_dir, "main.py")
    resp = await client.get(
        "/api/v1/files/browse/content",
        params={"path": py_path, "workspace": workspace_dir},
    )
    assert resp.status_code == 200
    ct = resp.headers.get("content-type", "")
    assert "text" in ct or "python" in ct


# -----------------------------------------------------------------------
# GET /browse/search — file name fuzzy search
# -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_search_basic(client: AsyncClient, workspace_dir: str):
    """Search finds files matching query."""
    resp = await client.get(
        "/api/v1/files/browse/search",
        params={"q": "main", "workspace": workspace_dir},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    names = [r["name"] for r in data["results"]]
    assert "main.py" in names


@pytest.mark.anyio
async def test_browse_search_returns_relative_path(client: AsyncClient, workspace_dir: str):
    """Search results include relative paths."""
    resp = await client.get(
        "/api/v1/files/browse/search",
        params={"q": "app", "workspace": workspace_dir},
    )
    assert resp.status_code == 200
    results = resp.json()["data"]["results"]
    app_result = next((r for r in results if r["name"] == "app.ts"), None)
    assert app_result is not None
    assert app_result["relative_path"] == os.path.join("src", "app.ts")


@pytest.mark.anyio
async def test_browse_search_case_insensitive(client: AsyncClient, workspace_dir: str):
    """Search is case-insensitive."""
    resp = await client.get(
        "/api/v1/files/browse/search",
        params={"q": "MAIN", "workspace": workspace_dir},
    )
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()["data"]["results"]]
    assert "main.py" in names


@pytest.mark.anyio
async def test_browse_search_filters_hidden(client: AsyncClient, workspace_dir: str):
    """Hidden files should not appear in search results."""
    resp = await client.get(
        "/api/v1/files/browse/search",
        params={"q": "hidden", "workspace": workspace_dir},
    )
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()["data"]["results"]]
    assert ".hidden_file" not in names


@pytest.mark.anyio
async def test_browse_search_empty_query_returns_all(client: AsyncClient, workspace_dir: str):
    """Empty query returns all visible files (up to limit)."""
    resp = await client.get(
        "/api/v1/files/browse/search",
        params={"q": "", "workspace": workspace_dir},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 3


@pytest.mark.anyio
async def test_browse_search_respects_limit(client: AsyncClient, workspace_dir: str):
    """Limit parameter caps result count."""
    resp = await client.get(
        "/api/v1/files/browse/search",
        params={"q": "", "workspace": workspace_dir, "limit": 1},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] <= 1


@pytest.mark.anyio
async def test_browse_search_rejects_dangerous_workspace(client: AsyncClient):
    """Dangerous workspace path should be rejected."""
    resp = await client.get(
        "/api/v1/files/browse/search",
        params={"q": "test", "workspace": "/etc"},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_browse_search_no_match(client: AsyncClient, workspace_dir: str):
    """Query that matches nothing returns empty results."""
    resp = await client.get(
        "/api/v1/files/browse/search",
        params={"q": "zzz_nonexistent_xyz", "workspace": workspace_dir},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["results"] == []


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _collect_names(entries: list[dict], _names: set[str] | None = None) -> set[str]:
    """Recursively collect all file/dir names from entry tree."""
    if _names is None:
        _names = set()
    for e in entries:
        _names.add(e["name"])
        if e.get("children"):
            _collect_names(e["children"], _names)
    return _names
