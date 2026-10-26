"""ima wire parsers and the client method table, against recorded payload shapes."""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.wiki.source_sync.ima.client import NOTES_PAGE_LIMIT, ImaClient
from app.services.wiki.source_sync.ima.errors import ImaPermanentError
from app.services.wiki.source_sync.ima.models import (
    ImaCredentials,
    parse_knowledge_bases,
    parse_list_page,
    parse_media_info,
    parse_notes_page,
)
from app.services.wiki.source_sync.ima.transport import ImaTransport

CREDENTIALS = ImaCredentials(client_id="c", api_key="k")


def test_list_page_separates_folders_from_documents_in_every_spelling() -> None:
    parsed = parse_list_page(
        {
            "knowledge_list": [
                {"media_id": "m1", "title": "a.pdf", "media_type": 1, "parent_folder_id": "f0"},
                {"media_id": "fold-typed", "title": "Typed", "media_type": 99},
                {"folder_id": "fold-bare", "name": "Bare"},
            ],
            "folder_list": [{"folder_id": "fold-listed", "name": "Listed"}],
            "next_cursor": "c2",
            "is_end": False,
        }
    )

    assert [(item.media_id, item.parent_folder_id, item.media_type) for item in parsed.items] == [("m1", "f0", 1)]
    assert {(folder.folder_id, folder.name) for folder in parsed.folders} == {
        ("fold-typed", "Typed"),
        ("fold-bare", "Bare"),
        ("fold-listed", "Listed"),
    }
    assert parsed.next_cursor == "c2" and parsed.is_end is False


def test_knowledge_bases_skip_entries_without_id_or_name() -> None:
    bases, cursor, is_end = parse_knowledge_bases(
        {"info_list": [{"id": "1", "name": "A"}, {"kb_id": "2", "kb_name": "B"}, {"id": "3"}], "is_end": True},
        "info_list",
    )
    assert [(base.id, base.name) for base in bases] == [("1", "A"), ("2", "B")]
    assert cursor == "" and is_end is True


def test_notes_page_skips_deleted_notes_and_unwraps_every_nesting() -> None:
    parsed = parse_notes_page(
        {
            "note_book_list": [
                {
                    "basic_info": {
                        "basic_info": {"docid": "n1", "title": "Plan", "folder_name": "Work", "modify_time": "1700000000000"}
                    }
                },
                {"basic_info": {"docid": "n2", "title": "Flat", "modify_time": 5}},
                {"docid": "n3", "title": "Bare"},
                {"basic_info": {"basic_info": {"docid": "gone", "status": 1}}},
            ],
            "next_cursor": "c2",
            "is_end": False,
        }
    )
    assert [(note.note_id, note.title, note.folder_name, note.modify_time) for note in parsed.notes] == [
        ("n1", "Plan", "Work", 1700000000000),
        ("n2", "Flat", "", 5),
        ("n3", "Bare", "", 0),
    ]
    assert parsed.next_cursor == "c2" and parsed.is_end is False


def test_notes_page_in_the_flat_shape_reads_the_note_id_and_the_notebook_from_the_extension_block() -> None:
    parsed = parse_notes_page(
        {
            "note_book_list": [
                {
                    "note_id": "n1",
                    "title": "Plan",
                    "summary": "short",
                    "modify_time": 1700000000000,
                    "note_ext_info": {"folder_id": "f1", "folder_name": "Work"},
                }
            ],
            "is_end": True,
        }
    )
    assert [(note.note_id, note.title, note.folder_name, note.modify_time) for note in parsed.notes] == [
        ("n1", "Plan", "Work", 1700000000000)
    ]


@pytest.mark.parametrize(
    "data",
    [
        {"note_book_list": [], "is_end": True},
        {
            "note_book_list": [{"basic_info": {"basic_info": {"docid": "gone", "status": 1}}}],
            "next_cursor": "c2",
            "is_end": False,
        },
    ],
    ids=["empty-account", "only-deleted-notes"],
)
def test_notes_page_without_live_notes_is_valid_when_nothing_was_unreadable(data: dict[str, object]) -> None:
    assert parse_notes_page(data).notes == ()


def test_notes_page_whose_entries_none_can_be_read_raises_instead_of_looking_empty() -> None:
    with pytest.raises(ImaPermanentError):
        parse_notes_page(
            {"note_book_list": [{"unknown_shape": {"id": "x"}}, {"basic_info": {"basic_info": {"status": 1}}}], "is_end": True}
        )


def test_media_info_reads_url_headers_and_note_id() -> None:
    info = parse_media_info(
        {
            "media_type": "6",
            "url_info": {"url": "https://x/y", "headers": {"Authorization": "sig", "X-Bad": ["list"]}},
            "notebook_ext_info": {"notebook_id": "nb1"},
        }
    )
    assert info.media_type == 6
    assert info.url == "https://x/y"
    assert info.headers == {"Authorization": "sig"}
    assert info.note_id == "nb1"


def _client(handler: httpx.MockTransport) -> ImaClient:
    return ImaClient(ImaTransport(CREDENTIALS, transport=handler))


async def test_list_knowledge_bases_unions_both_endpoints_sorted_and_deduplicated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("get_addable_knowledge_base_list"):
            data = {"addable_knowledge_base_list": [{"id": "2", "name": "beta"}, {"id": "1", "name": "Alpha"}], "is_end": True}
        else:
            data = {"info_list": [{"id": "1", "name": "Alpha"}, {"id": "3", "name": "gamma"}], "is_end": True}
        return httpx.Response(200, json={"retcode": 0, "data": data})

    bases = await _client(httpx.MockTransport(handler)).list_knowledge_bases()
    assert [base.id for base in bases] == ["1", "2", "3"]


async def test_list_knowledge_bases_stops_on_a_repeated_cursor() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "retcode": 0,
                "data": {"addable_knowledge_base_list": [], "info_list": [], "next_cursor": "same", "is_end": False},
            },
        )

    await _client(httpx.MockTransport(handler)).list_knowledge_bases()
    # Each of the two endpoints is asked twice: the first page, then the page its cursor points to, then it stops.
    assert calls == 4


async def test_notes_listing_and_plain_text_body_request_shapes() -> None:
    bodies: list[dict[str, object]] = []
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        paths.append(request.url.path)
        if request.url.path.endswith("get_doc_content"):
            return httpx.Response(200, json={"retcode": 0, "data": {"content": "  hello  "}})
        return httpx.Response(200, json={"retcode": 0, "data": {"note_book_list": [], "next_cursor": "", "is_end": True}})

    client = _client(httpx.MockTransport(handler))
    await client.list_notes_page(cursor="abc")
    assert await client.get_note_text("n1") == "hello"

    assert paths[0].endswith("/note/v1/list_note_by_folder_id")
    assert bodies[0] == {"folder_id": "", "cursor": "abc", "limit": NOTES_PAGE_LIMIT}
    assert NOTES_PAGE_LIMIT <= 20  # ima's documented ceiling for the notes listing
    assert bodies[1]["target_content_format"] == 0
