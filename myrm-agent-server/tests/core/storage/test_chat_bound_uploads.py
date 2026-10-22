"""Uploads that an incognito chat binds to itself, and the page images extracted from them."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.api.files import pdf_extract
from app.core.storage import FilePurpose, FilesService
from app.core.storage.chat_bound import (
    chat_bound_uploads,
    delete_uploads_with_derivatives,
    derivatives_of,
    pdf_extract_source,
)


@pytest.fixture
def service(tmp_path: Path) -> FilesService:
    return FilesService(LocalStorageBackend(tmp_path))


async def _page_image(service: FilesService, upload_id: str) -> str:
    saved = await service.save_generated_file("pdf-page-1.png", b"png", "image/png", source_chat_id=pdf_extract_source(upload_id))
    return saved.id


async def _on_disk(service: FilesService) -> set[str]:
    return {file.id for file in await service.list_files(include_expired=True)}


@pytest.mark.asyncio
async def test_an_upload_remembers_the_chat_it_was_bound_to(service: FilesService) -> None:
    bound = await service.upload_file("tax.pdf", b"x", source_chat_id="chat-1")
    free = await service.upload_file("notes.txt", b"y")

    reloaded = await service.get_file(bound.id)

    assert reloaded is not None
    assert reloaded.source_chat_id == "chat-1"
    assert free.source_chat_id is None


@pytest.mark.asyncio
async def test_chat_bound_uploads_selects_only_uploads_that_carry_a_chat(service: FilesService) -> None:
    mine = await service.upload_file("a.txt", b"a", source_chat_id="chat-1")
    other_chat = await service.upload_file("b.txt", b"b", source_chat_id="chat-2")
    unbound = await service.upload_file("c.txt", b"c")
    # A generated file naming a chat is not an upload: its lifecycle is the 7-day expiry.
    generated = await service.save_generated_file("d.txt", b"d", source_chat_id="chat-1")

    files = await service.list_files(include_expired=True)

    assert {f.id for f in chat_bound_uploads(files)} == {mine.id, other_chat.id}
    assert {unbound.id, generated.id}.isdisjoint(f.id for f in chat_bound_uploads(files))


@pytest.mark.asyncio
async def test_derivatives_of_picks_the_page_images_of_those_uploads_only(service: FilesService) -> None:
    upload = await service.upload_file("scan.pdf", b"x", source_chat_id="chat-1")
    other = await service.upload_file("other.pdf", b"x")
    page = await _page_image(service, upload.id)
    other_page = await _page_image(service, other.id)
    kanban = await service.save_generated_file("k.txt", b"k", source_chat_id="kanban:task-1")

    files = await service.list_files(include_expired=True)

    assert [f.id for f in derivatives_of([upload], files)] == [page]
    assert {other_page, kanban.id}.isdisjoint(f.id for f in derivatives_of([upload], files))


@pytest.mark.asyncio
async def test_deleting_uploads_removes_their_page_images_and_nothing_else(service: FilesService) -> None:
    doomed = await service.upload_file("scan.pdf", b"x", source_chat_id="chat-1")
    survivor = await service.upload_file("keep.pdf", b"x")
    doomed_page = await _page_image(service, doomed.id)
    survivor_page = await _page_image(service, survivor.id)

    removed = await delete_uploads_with_derivatives(service, [doomed])

    assert removed == 2
    assert await _on_disk(service) == {survivor.id, survivor_page}
    for gone in (doomed.id, doomed_page):
        with pytest.raises(FileNotFoundError):  # content and sidecar are both removed
            await service.get_content(gone)


@pytest.mark.asyncio
async def test_deleting_nothing_does_not_scan_the_store(service: FilesService, monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(*_args: object, **_kwargs: object) -> list[object]:
        raise AssertionError("an empty deletion must not list files")

    monkeypatch.setattr(service, "list_files", forbidden)

    assert await delete_uploads_with_derivatives(service, []) == 0


@pytest.mark.asyncio
async def test_a_file_that_cannot_be_deleted_is_skipped_and_the_rest_still_go(
    service: FilesService, monkeypatch: pytest.MonkeyPatch
) -> None:
    stuck = await service.upload_file("stuck.pdf", b"x", source_chat_id="chat-1")
    fine = await service.upload_file("fine.pdf", b"x", source_chat_id="chat-1")
    real_delete = service.delete_file

    async def flaky(file_id: str) -> bool:
        if file_id == stuck.id:
            raise OSError("disk error")
        return await real_delete(file_id)

    monkeypatch.setattr(service, "delete_file", flaky)

    assert await delete_uploads_with_derivatives(service, [stuck, fine]) == 1
    assert await _on_disk(service) == {stuck.id}


@pytest.mark.asyncio
async def test_the_pdf_extract_api_marks_page_images_the_way_the_cleanup_looks_for_them(
    service: FilesService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pdf_extract, "is_local_mode", lambda: False)
    monkeypatch.setattr(pdf_extract, "files_service", service)
    upload = await service.upload_file("scan.pdf", b"x", source_chat_id="chat-1")
    image = SimpleNamespace(data=base64.b64encode(b"png").decode(), mime_type="image/png")
    body = pdf_extract.PDFExtractRequest(file_id=upload.id)

    items = await pdf_extract._persist_pdf_images([image], body)

    assert items[0].file_url is not None
    files = await service.list_files(purpose=FilePurpose.GENERATED, include_expired=True)
    assert [f.id for f in derivatives_of([upload], files)] == [f.id for f in files]
