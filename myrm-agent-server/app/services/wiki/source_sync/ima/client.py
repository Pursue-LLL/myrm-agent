"""Method table over the ima knowledge-base and notes OpenAPI.

[INPUT]
- .transport::ImaTransport (POS: authenticated POST + envelope handling)
- .models (POS: wire payload parsers)

[OUTPUT]
- ImaClient: verify / list_knowledge_bases / list_knowledge_page / get_media_info / get_note_text / list_notes_page

[POS]
Read-only ima access. The sync lane never writes to or deletes from a user's ima library.
"""

from __future__ import annotations

from .errors import ImaPermanentError
from .models import (
    ImaKnowledgeBase,
    ImaListPage,
    ImaMediaInfo,
    ImaNotesPage,
    JsonObject,
    parse_knowledge_bases,
    parse_list_page,
    parse_media_info,
    parse_notes_page,
)
from .transport import NOTE_PREFIX, WIKI_PREFIX, ImaTransport

KB_PAGE_LIMIT = 50
KB_SEARCH_PAGE_LIMIT = 20
LIST_PAGE_LIMIT = 50
NOTES_PAGE_LIMIT = 20  # ima documents 20 as the ceiling of its notes listing

_MAX_KB_PAGES = 200
_NOTE_FORMAT_PLAIN_TEXT = 0


class ImaClient:
    def __init__(self, transport: ImaTransport) -> None:
        self._transport = transport

    async def verify(self) -> None:
        """Cheapest authenticated call; raises ``ImaAuthError`` for rejected credentials."""
        await self._transport.post(WIKI_PREFIX, "get_addable_knowledge_base_list", {"cursor": "", "limit": 1})

    async def list_knowledge_bases(self) -> list[ImaKnowledgeBase]:
        """Every knowledge base the credentials can reach.

        ``get_addable_knowledge_base_list`` and ``search_knowledge_base`` each have been observed to miss
        libraries the other returns, so the result is their union.
        """
        found: dict[str, ImaKnowledgeBase] = {}
        for method, array_key, limit, body_extra in (
            ("get_addable_knowledge_base_list", "addable_knowledge_base_list", KB_PAGE_LIMIT, {}),
            ("search_knowledge_base", "info_list", KB_SEARCH_PAGE_LIMIT, {"query": ""}),
        ):
            cursor = ""
            seen_cursors: set[str] = set()
            for _ in range(_MAX_KB_PAGES):
                data = await self._transport.post(WIKI_PREFIX, method, {"cursor": cursor, "limit": limit, **body_extra})
                bases, next_cursor, is_end = parse_knowledge_bases(data, array_key)
                for base in bases:
                    found.setdefault(base.id, base)
                if is_end or not next_cursor or next_cursor in seen_cursors:
                    break
                seen_cursors.add(next_cursor)
                cursor = next_cursor
        return sorted(found.values(), key=lambda base: base.name.casefold())

    async def list_knowledge_page(self, kb_id: str, *, folder_id: str = "", cursor: str = "") -> ImaListPage:
        body: JsonObject = {"knowledge_base_id": kb_id, "cursor": cursor, "limit": LIST_PAGE_LIMIT}
        if folder_id:
            body["folder_id"] = folder_id
        return parse_list_page(await self._transport.post(WIKI_PREFIX, "get_knowledge_list", body))

    async def get_media_info(self, media_id: str) -> ImaMediaInfo:
        return parse_media_info(await self._transport.post(WIKI_PREFIX, "get_media_info", {"media_id": media_id}))

    async def get_note_text(self, note_id: str) -> str:
        """A note's body as plain text; ima only reliably supports the plain-text target format."""
        if not note_id:
            raise ImaPermanentError("ima note id is missing")
        data = await self._transport.post(
            NOTE_PREFIX,
            "get_doc_content",
            {"doc_id": note_id, "note_id": note_id, "target_content_format": _NOTE_FORMAT_PLAIN_TEXT},
        )
        return str(data.get("content") or "").strip()

    async def list_notes_page(self, *, cursor: str) -> ImaNotesPage:
        """One page of the notes listing; an empty ``folder_id`` lists every note and the first page takes an empty cursor."""
        data = await self._transport.post(
            NOTE_PREFIX,
            "list_note_by_folder_id",
            {"folder_id": "", "cursor": cursor, "limit": NOTES_PAGE_LIMIT},
        )
        return parse_notes_page(data)
