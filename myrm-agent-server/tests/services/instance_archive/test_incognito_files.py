"""What a web incognito chat wrote to disk stays out of every export, and so does the subagent checkpoint store.

Tool calls are not gated in an incognito chat: the agent writes files into the chat's workspace like in any other
chat, and subagent runs persist their conversation in a store that is keyed by task, not by chat. Both would
otherwise travel in an export or an automatic backup although the chat row and its messages are scrubbed.
"""

from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

import pytest
from myrm_agent_harness.agent.sub_agents.checkpointer import resolve_subagent_checkpoint_db_path
from myrm_agent_harness.toolkits.code_execution import create_workspace_service

from app.platform_utils.workspace_session import CHAT_SESSION_PREFIX
from app.services.agent.params.workspace_resolve import default_chat_workspace_path
from app.services.instance_archive import export_service, policy
from app.services.instance_archive.export_service import ExportError, build_export
from app.services.instance_archive.incognito_workspaces import WORKSPACES_REL, without_incognito_workspaces
from app.services.instance_archive.policy import SourceFile, StateScan

SECRET = "incognito_secret_file_text"
KEPT = "ordinary_kept_file_text"
WORKSPACES = "/".join(WORKSPACES_REL)
_PAYLOAD_DIR = "payload/"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sqlite_with(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE checkpoints (payload TEXT)")
    conn.execute("INSERT INTO checkpoints VALUES (?)", (text,))
    conn.commit()
    conn.close()


def _state_dir(root: Path) -> Path:
    """An instance with one web incognito chat, one ordinary chat and one imported transcript, each with a workspace."""
    state = root / "state"
    state.mkdir()
    conn = sqlite3.connect(state / "data.db")
    conn.executescript(
        """
        CREATE TABLE _schema_migrations (version INTEGER);
        INSERT INTO _schema_migrations VALUES (1);
        CREATE TABLE chats (id TEXT PRIMARY KEY, is_incognito BOOLEAN, source TEXT);
        INSERT INTO chats VALUES ('incognito', 1, 'web'), ('kept', 0, 'web'), ('imported', 1, 'claude_code');
        """
    )
    conn.commit()
    conn.close()
    workspaces = state / WORKSPACES
    _write(workspaces / "chat_incognito" / "report.md", SECRET)
    _write(workspaces / "chat_incognito" / "src" / "deep" / "notes.txt", SECRET)
    _write(workspaces / "chat_incognito" / "_metadata.json", "{}")
    _write(workspaces / "chat_kept" / "report.md", KEPT)
    _write(workspaces / "chat_imported" / "report.md", KEPT)
    # A directory that merely starts with an incognito chat's workspace name belongs to another chat.
    _write(workspaces / "chat_incognito-2" / "report.md", KEPT)
    return state


def _export(state: Path, dest: Path) -> dict[str, bytes]:
    """The archive's payload by state-directory-relative path."""
    result = build_export(
        state_dir=state, dest=dest, user_id="user-a", app_version="1.0.0", deploy_mode="local", config_key=None, passphrase=None
    )
    with zipfile.ZipFile(result.path) as archive:
        return {
            name.removeprefix(_PAYLOAD_DIR): archive.read(name) for name in archive.namelist() if name.startswith(_PAYLOAD_DIR)
        }


def test_the_workspace_files_of_a_web_incognito_chat_are_not_exported(tmp_path: Path) -> None:
    members = _export(_state_dir(tmp_path), tmp_path / "out.zip")

    assert f"{WORKSPACES}/chat_kept/report.md" in members  # the names below are read the way the archive spells them
    assert [name for name in members if name.startswith(f"{WORKSPACES}/chat_incognito/")] == []
    assert [name for name, data in members.items() if SECRET.encode() in data] == []


def test_every_other_workspace_still_travels(tmp_path: Path) -> None:
    members = _export(_state_dir(tmp_path), tmp_path / "out.zip")

    for chat in ("chat_kept", "chat_imported", "chat_incognito-2"):  # the imported transcript is real data
        assert members[f"{WORKSPACES}/{chat}/report.md"] == KEPT.encode()


def test_the_subagent_checkpoint_store_is_not_exported_wherever_it_sits(tmp_path: Path) -> None:
    state = _state_dir(tmp_path)
    for location in (Path("data"), Path(".")):  # the default data directory, or one that is the state directory itself
        _sqlite_with(state / location / "subagent_checkpoints.sqlite", SECRET)

    members = _export(state, tmp_path / "out.zip")

    assert "data.db" in members
    assert not any(name.endswith("subagent_checkpoints.sqlite") for name in members)
    assert [name for name, data in members.items() if SECRET.encode() in data] == []


def test_an_export_that_cannot_tell_which_chats_are_incognito_fails_instead_of_carrying_every_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreadable(_main_db: Path) -> list[str]:
        raise sqlite3.OperationalError("database is locked")

    state = _state_dir(tmp_path)
    monkeypatch.setattr(export_service, "live_web_incognito_chat_ids", unreadable)

    with pytest.raises(ExportError):
        _export(state, tmp_path / "out.zip")
    assert not (tmp_path / "out.zip").exists()


def test_unreadable_files_of_an_incognito_workspace_are_not_reported_as_missing_from_the_archive() -> None:
    inside = f"{WORKSPACES}/chat_incognito/locked.bin"
    outside = f"{WORKSPACES}/chat_kept/locked.bin"
    scan = StateScan(
        sources=[
            SourceFile(f"{WORKSPACES}/chat_incognito/a.txt", Path("a"), 1, False),
            SourceFile("data.db", Path("d"), 1, True),
        ],
        excluded=[],
        unreadable=[inside, outside],
    )

    result = without_incognito_workspaces(scan, ["incognito"])

    assert [source.rel for source in result.sources] == ["data.db"]
    assert result.unreadable == [outside]


def test_no_incognito_chat_leaves_the_scan_untouched() -> None:
    scan = StateScan(sources=[SourceFile(f"{WORKSPACES}/chat_a/a.txt", Path("a"), 1, False)], excluded=[], unreadable=[])

    assert without_incognito_workspaces(scan, []) is scan


# --- pins to the places the rules above are derived from ------------------------------------------------------


def test_the_workspace_location_is_where_the_runtime_creates_it(tmp_path: Path) -> None:
    assert create_workspace_service(root_dir=tmp_path / "harness").workspaces_root == tmp_path / WORKSPACES
    assert default_chat_workspace_path("some-chat").name == f"{CHAT_SESSION_PREFIX}some-chat"


def test_the_subagent_store_file_name_is_the_one_the_checkpointer_uses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("SUBAGENT_CHECKPOINT_DB_PATH", "PYTEST_CURRENT_TEST", "TESTING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))

    assert Path(resolve_subagent_checkpoint_db_path()).name in policy._RUNTIME_FILE_NAMES
