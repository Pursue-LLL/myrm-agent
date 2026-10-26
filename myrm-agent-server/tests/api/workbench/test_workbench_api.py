"""[INPUT]
- TestClient from starlette/fastapi test suite
- Workbench API routes under /api/v1/workbench
- tests.support.chat_workspace::chats_bound_to_workspaces (POS: binds a chat to a tmp workspace)

[OUTPUT]
- Tests verifying the workbench is confined to the named chat's workspace: file tree, file content and terminal exec

[POS]
Tests for the auxiliary workbench backend: root resolution, path confinement, command gate, timeout and output cap.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.workbench.models import TerminalExecRequest
from app.api.workbench.routes import _MAX_RESPONSE_BYTES, execute_terminal_command, workbench_router
from tests.support.chat_workspace import chats_bound_to_workspaces

PREFIX = "/api/v1/workbench"
CHAT = "chat-wb"
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="relies on POSIX process groups and coreutils")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "notes.md").write_text("# notes\n", encoding="utf-8")
    (root / ".hidden").write_text("secret", encoding="utf-8")
    return root


@pytest.fixture
def client(workspace: Path) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(workbench_router, prefix=PREFIX)
    with chats_bound_to_workspaces({CHAT: workspace}):
        yield TestClient(app)


def test_file_tree_lists_the_chats_workspace_with_relative_paths(client: TestClient, workspace: Path) -> None:
    response = client.get(f"{PREFIX}/files", params={"chat_id": CHAT})

    assert response.status_code == 200
    data = response.json()
    assert "root_path" not in data
    assert [node["path"] for node in data["nodes"]] == ["src", "notes.md"]
    assert data["nodes"][0]["children"][0]["path"] == os.path.join("src", "app.py")
    assert (data["total_files"], data["total_dirs"]) == (2, 1)


def test_file_tree_requires_a_chat(client: TestClient) -> None:
    assert client.get(f"{PREFIX}/files").status_code == 422


def test_a_chat_without_a_workspace_directory_gets_404(client: TestClient, tmp_path: Path) -> None:
    with chats_bound_to_workspaces({"chat-empty": tmp_path / "never-created"}):
        response = client.get(f"{PREFIX}/files", params={"chat_id": "chat-empty"})

    assert response.status_code == 404


def test_a_chat_id_that_cannot_name_a_workspace_gets_404_not_the_process_directory(client: TestClient) -> None:
    with chats_bound_to_workspaces({}):
        response = client.get(f"{PREFIX}/files", params={"chat_id": "../.."})

    assert response.status_code == 404


def test_file_tree_path_traversal_blocked(client: TestClient) -> None:
    response = client.get(f"{PREFIX}/files", params={"chat_id": CHAT, "root_dir": "../../../../etc"})

    assert response.status_code == 403
    assert "traversal forbidden" in response.json()["detail"].lower()


def test_file_content_reads_inside_the_workspace_only(client: TestClient, workspace: Path) -> None:
    ok = client.get(f"{PREFIX}/file/content", params={"chat_id": CHAT, "path": "src/app.py"})
    assert ok.status_code == 200
    assert ok.json()["language"] == "python"
    assert ok.json()["content"] == "print('hi')\n"
    assert ok.json()["path"] == os.path.join("src", "app.py")
    assert ok.json()["is_binary"] is False
    assert ok.json()["truncated"] is False

    assert client.get(f"{PREFIX}/file/content", params={"chat_id": CHAT, "path": "missing.py"}).status_code == 404
    outside = workspace.parent / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    escape = client.get(f"{PREFIX}/file/content", params={"chat_id": CHAT, "path": str(outside)})
    assert escape.status_code == 403


def test_a_binary_file_is_reported_instead_of_decoded(client: TestClient, workspace: Path) -> None:
    (workspace / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + os.urandom(64))

    response = client.get(f"{PREFIX}/file/content", params={"chat_id": CHAT, "path": "logo.png"})

    assert response.status_code == 200
    body = response.json()
    assert body["is_binary"] is True
    assert body["content"] == ""
    assert body["size_bytes"] > 0


def test_a_large_text_file_is_read_up_to_the_cap_and_flagged(client: TestClient, workspace: Path) -> None:
    (workspace / "big.txt").write_text("a" + "\u00e9" * _MAX_RESPONSE_BYTES, encoding="utf-8")

    response = client.get(f"{PREFIX}/file/content", params={"chat_id": CHAT, "path": "big.txt"})

    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is True
    assert body["size_bytes"] == 1 + 2 * _MAX_RESPONSE_BYTES
    assert 0 < len(body["content"].encode("utf-8")) <= _MAX_RESPONSE_BYTES
    assert "\ufffd" not in body["content"], "the cut must not leave half a character behind"


@posix_only
def test_a_symlink_out_of_the_workspace_is_not_followed(client: TestClient, workspace: Path) -> None:
    outside = workspace.parent / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    (workspace / "link.txt").symlink_to(outside)

    response = client.get(f"{PREFIX}/file/content", params={"chat_id": CHAT, "path": "link.txt"})

    assert response.status_code == 403


def test_terminal_runs_in_the_chats_workspace(client: TestClient, workspace: Path) -> None:
    pwd = "cd" if sys.platform == "win32" else "pwd"
    response = client.post(f"{PREFIX}/terminal/exec", json={"chat_id": CHAT, "command": pwd, "timeout_seconds": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] == 0
    assert Path(body["stdout"].strip()).resolve() == workspace.resolve()
    assert body["truncated"] is False


@posix_only
def test_terminal_does_not_inherit_the_servers_credentials(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-canary-must-not-leak")
    command = 'echo "key=${OPENAI_API_KEY:-absent} path=${PATH:+present}"'

    response = client.post(f"{PREFIX}/terminal/exec", json={"chat_id": CHAT, "command": command, "timeout_seconds": 10})

    assert response.status_code == 200
    assert response.json()["stdout"].strip() == "key=absent path=present"


def test_terminal_cwd_is_confined_to_the_workspace(client: TestClient) -> None:
    escape = client.post(f"{PREFIX}/terminal/exec", json={"chat_id": CHAT, "command": "echo x", "cwd": ".."})
    assert escape.status_code == 403

    missing = client.post(f"{PREFIX}/terminal/exec", json={"chat_id": CHAT, "command": "echo x", "cwd": "nope"})
    assert missing.status_code == 400


@pytest.mark.parametrize("command", ["rm -rf /", "rm -fr /", "rm -r -f /", "rm -rf ~", "mkfs.ext4 /dev/sda1"])
def test_terminal_refuses_destructive_commands(client: TestClient, command: str) -> None:
    response = client.post(f"{PREFIX}/terminal/exec", json={"chat_id": CHAT, "command": command})

    assert response.status_code == 400
    assert "safety guard" in response.json()["detail"].lower()


@posix_only
def test_terminal_allows_ordinary_cleanup_inside_the_workspace(client: TestClient, workspace: Path) -> None:
    (workspace / "build-cache").mkdir()

    response = client.post(f"{PREFIX}/terminal/exec", json={"chat_id": CHAT, "command": "rm -rf /tmp/never-exists-myrm"})
    assert response.status_code == 200

    response = client.post(f"{PREFIX}/terminal/exec", json={"chat_id": CHAT, "command": "rm -rf ./build-cache"})
    assert response.status_code == 200
    assert not (workspace / "build-cache").exists()


@posix_only
def test_terminal_does_not_read_the_servers_stdin(client: TestClient) -> None:
    response = client.post(f"{PREFIX}/terminal/exec", json={"chat_id": CHAT, "command": "cat", "timeout_seconds": 5})

    assert response.status_code == 200
    assert response.json()["stdout"] == ""


@posix_only
def test_timeout_kills_the_whole_process_tree(client: TestClient, workspace: Path) -> None:
    pid_file = workspace / "child.pid"
    command = f"sh -c 'echo $$ > {pid_file}; exec sleep 300' & wait"

    response = client.post(f"{PREFIX}/terminal/exec", json={"chat_id": CHAT, "command": command, "timeout_seconds": 1})

    assert response.status_code == 408
    child = int(pid_file.read_text().strip())
    try:
        os.kill(child, 0)
    except ProcessLookupError:
        return
    pytest.fail(f"process {child} survived the timeout")


@posix_only
async def test_cancelling_the_handler_task_kills_the_whole_process_tree(workspace: Path) -> None:
    pid_file = workspace / "child.pid"
    request = TerminalExecRequest(
        chat_id=CHAT,
        command=f"sh -c 'echo $$ > {pid_file}; exec sleep 300' & wait",
        timeout_seconds=60,
    )
    with chats_bound_to_workspaces({CHAT: workspace}):
        running = asyncio.create_task(execute_terminal_command(request))
        for _ in range(100):
            if pid_file.exists() and pid_file.read_text().strip():
                break
            await asyncio.sleep(0.05)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running

    child = int(pid_file.read_text().strip())
    for _ in range(40):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.05)
    os.kill(child, 9)
    pytest.fail(f"process {child} survived the cancelled handler task")


@posix_only
def test_output_beyond_the_cap_is_cut_and_flagged(client: TestClient) -> None:
    command = f"head -c {_MAX_RESPONSE_BYTES * 3} /dev/zero | tr '\\0' 'a'"

    response = client.post(f"{PREFIX}/terminal/exec", json={"chat_id": CHAT, "command": command, "timeout_seconds": 30})

    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is True
    assert len(body["stdout"]) == _MAX_RESPONSE_BYTES
