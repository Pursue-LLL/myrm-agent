"""FilesService.save_file_reference: one physical file of a chat keeps one id."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.storage.models import File
from app.core.storage.paths import get_file_metadata_path
from app.core.storage.service import FilesService


@pytest.fixture
def service(tmp_path: Path) -> FilesService:
    return FilesService(storage=LocalStorageBackend(tmp_path / "storage"))


def _page(directory: Path, name: str = "index.html") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    page = directory / name
    page.write_text("<h1>page</h1>", encoding="utf-8")
    return page


async def _register(service: FilesService, path: Path | str, chat_id: str = "chat-1", size: int = 13) -> File:
    return await service.save_file_reference(chat_id, Path(path).name, str(path), size)


@pytest.mark.asyncio
async def test_registering_the_same_file_again_returns_the_same_id(service: FilesService, tmp_path: Path) -> None:
    page = _page(tmp_path / "proj")

    first = await _register(service, page)
    second = await _register(service, page)

    assert first.id == second.id
    assert first.storage_path == second.storage_path


@pytest.mark.asyncio
async def test_every_spelling_of_a_path_names_the_same_file(
    service: FilesService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = _page(tmp_path / "proj")
    monkeypatch.chdir(tmp_path)

    spellings = [
        "proj/index.html",
        "./proj/index.html",
        "proj/../proj/index.html",
        str(page),
        f"{tmp_path}/proj/../proj/index.html",
    ]
    ids = {(await _register(service, spelling)).id for spelling in spellings}

    assert len(ids) == 1


@pytest.mark.skipif(os.name == "nt", reason="creating symlinks needs elevated rights on Windows")
@pytest.mark.asyncio
async def test_a_symlink_and_its_target_are_the_same_file(service: FilesService, tmp_path: Path) -> None:
    page = _page(tmp_path / "proj")
    link = tmp_path / "shortcut.html"
    link.symlink_to(page)

    assert (await _register(service, link)).id == (await _register(service, page)).id


@pytest.mark.asyncio
async def test_files_whose_paths_differ_only_by_a_workspace_directory_stay_distinct(
    service: FilesService, tmp_path: Path
) -> None:
    pages = [
        _page(tmp_path / "workspace" / "proj"),
        _page(tmp_path / "proj"),
        _page(tmp_path / "team-workspace" / "proj"),
        _page(tmp_path / "team-proj"),
    ]

    ids = {(await _register(service, page)).id for page in pages}

    assert len(ids) == len(pages)


@pytest.mark.asyncio
async def test_the_same_file_has_one_id_per_chat(service: FilesService, tmp_path: Path) -> None:
    page = _page(tmp_path / "proj")

    first = await _register(service, page, chat_id="chat-1")
    other = await _register(service, page, chat_id="chat-2")

    assert first.id != other.id
    assert (await _register(service, page, chat_id="chat-2")).id == other.id


@pytest.mark.asyncio
async def test_registering_again_refreshes_the_record_but_keeps_id_and_creation_time(
    service: FilesService, tmp_path: Path
) -> None:
    page = _page(tmp_path / "proj")
    first = await _register(service, page, size=13)

    page.write_text("<h1>a much longer page than before</h1>", encoding="utf-8")
    second = await _register(service, page, size=39)

    stored = json.loads(await service.storage.read_text(get_file_metadata_path(second.storage_path)))
    assert second.id == first.id
    assert second.created_at == first.created_at
    assert stored["id"] == first.id
    assert stored["size"] == 39


@pytest.mark.asyncio
async def test_an_unreadable_record_is_replaced_instead_of_blocking_the_file(service: FilesService, tmp_path: Path) -> None:
    page = _page(tmp_path / "proj")
    first = await _register(service, page)
    await service.storage.write_text(get_file_metadata_path(first.storage_path), '{"id": "file_x", "purpose": ')

    recovered = await _register(service, page)

    assert recovered.id != ""
    assert (await _register(service, page)).id == recovered.id


@pytest.mark.asyncio
async def test_concurrent_registrations_of_a_new_file_share_one_id(service: FilesService, tmp_path: Path) -> None:
    page = _page(tmp_path / "proj")

    files = await asyncio.gather(*(_register(service, page) for _ in range(8)))

    assert len({file.id for file in files}) == 1
