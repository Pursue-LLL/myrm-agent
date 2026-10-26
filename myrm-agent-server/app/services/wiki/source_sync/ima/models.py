"""Typed views over ima's loosely-typed wire payloads, and the parsers that produce them.

[INPUT]
- .errors::ImaPermanentError (POS: failure taxonomy; a notes page in an unrecognized shape raises it)

[OUTPUT]
- ImaCredentials / ImaKnowledgeBase / ImaEntry / ImaFolder / ImaListPage / ImaMediaInfo / ImaNote / ImaNotesPage
- parse_knowledge_bases / parse_list_page / parse_media_info / parse_notes_page
- media type constants: MEDIA_NOTE, MEDIA_WEB_TYPES, MEDIA_FILE_EXTENSIONS, MEDIA_LABELS

[POS]
The single place that knows ima's field spellings. ima mixes documents and folders in one list and names the
same fields differently across endpoints, so every spelling seen in Tencent's own connector and live
responses is accepted here and nowhere else.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .errors import ImaPermanentError

type JsonObject = dict[str, object]

MEDIA_FOLDER = 99
MEDIA_NOTE = 11
MEDIA_HTML = 20
MEDIA_WEB_TYPES = frozenset({2, 6})

MEDIA_FILE_EXTENSIONS: dict[int, str] = {
    1: ".pdf",
    3: ".docx",
    4: ".pptx",
    5: ".xlsx",
    7: ".md",
    13: ".txt",
    21: ".epub",
}

MEDIA_LABELS: dict[int, str] = {
    1: "pdf",
    2: "web",
    3: "word",
    4: "ppt",
    5: "excel",
    6: "wechat",
    7: "markdown",
    9: "image",
    11: "note",
    12: "ai_session",
    13: "text",
    14: "xmind",
    15: "audio",
    16: "video",
    20: "html",
    21: "epub",
}


@dataclass(frozen=True, slots=True)
class ImaCredentials:
    client_id: str
    api_key: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ImaKnowledgeBase:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class ImaEntry:
    """One document in a knowledge base listing."""

    media_id: str
    title: str
    parent_folder_id: str
    media_type: int | None


@dataclass(frozen=True, slots=True)
class ImaFolder:
    folder_id: str
    name: str


@dataclass(frozen=True, slots=True)
class ImaListPage:
    items: tuple[ImaEntry, ...] = ()
    folders: tuple[ImaFolder, ...] = ()
    next_cursor: str = ""
    is_end: bool = True


@dataclass(frozen=True, slots=True)
class ImaMediaInfo:
    media_type: int | None
    url: str
    headers: dict[str, str]
    note_id: str


@dataclass(frozen=True, slots=True)
class ImaNote:
    note_id: str
    title: str
    folder_name: str
    modify_time: int


@dataclass(frozen=True, slots=True)
class ImaNotesPage:
    notes: tuple[ImaNote, ...] = ()
    next_cursor: str = ""
    is_end: bool = True


def _text(raw: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _entries(data: Mapping[str, object], *keys: str) -> list[Mapping[str, object]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    return []


def parse_knowledge_bases(data: Mapping[str, object], *keys: str) -> tuple[list[ImaKnowledgeBase], str, bool]:
    """Decode one page of a knowledge-base listing; *keys* names the array under which entries arrive."""
    bases: list[ImaKnowledgeBase] = []
    for raw in _entries(data, *keys):
        kb_id = _text(raw, "id", "kb_id")
        name = _text(raw, "name", "kb_name")
        if kb_id and name:
            bases.append(ImaKnowledgeBase(id=kb_id, name=name))
    return bases, _text(data, "next_cursor"), bool(data.get("is_end"))


def parse_list_page(data: Mapping[str, object]) -> ImaListPage:
    """Split a ``get_knowledge_list`` page into documents and folders.

    A folder is an entry typed ``99`` (its ``media_id`` is the folder id) or one that carries a ``folder_id``
    and no ``media_id``; either spelling has been observed.
    """
    items: list[ImaEntry] = []
    folders: list[ImaFolder] = []
    for raw in _entries(data, "knowledge_list", "info_list"):
        media_id = _text(raw, "media_id")
        media_type = _int(raw.get("media_type"))
        folder_id = _text(raw, "folder_id")
        if media_type == MEDIA_FOLDER or (folder_id and not media_id):
            resolved_id = folder_id or media_id
            if resolved_id:
                folders.append(ImaFolder(folder_id=resolved_id, name=_text(raw, "name", "title") or resolved_id))
            continue
        title = _text(raw, "title")
        if media_id:
            items.append(
                ImaEntry(
                    media_id=media_id,
                    title=title or media_id,
                    parent_folder_id=_text(raw, "parent_folder_id"),
                    media_type=media_type,
                )
            )
    for raw in _entries(data, "folder_list", "folders"):
        folder_id = _text(raw, "folder_id", "media_id")
        if folder_id:
            folders.append(ImaFolder(folder_id=folder_id, name=_text(raw, "name", "title") or folder_id))
    return ImaListPage(
        items=tuple(items),
        folders=tuple(folders),
        next_cursor=_text(data, "next_cursor"),
        is_end=bool(data.get("is_end")),
    )


def parse_media_info(data: Mapping[str, object]) -> ImaMediaInfo:
    url_info = data.get("url_info")
    url = ""
    headers: dict[str, str] = {}
    if isinstance(url_info, Mapping):
        url = _text(url_info, "url")
        raw_headers = url_info.get("headers")
        if isinstance(raw_headers, Mapping):
            headers = {str(k): str(v) for k, v in raw_headers.items() if isinstance(v, str | int | float)}
    note_info = data.get("notebook_ext_info")
    note_id = _text(note_info, "notebook_id", "doc_id") if isinstance(note_info, Mapping) else ""
    return ImaMediaInfo(media_type=_int(data.get("media_type")), url=url, headers=headers, note_id=note_id)


def _basic_info(raw: Mapping[str, object]) -> Mapping[str, object]:
    """Peel the ``basic_info`` wrappers around a listed note; one spelling nests them twice, another has none."""
    node = raw
    while isinstance(inner := node.get("basic_info"), Mapping):
        node = inner
    return node


def _notebook_name(note: Mapping[str, object]) -> str:
    """The notebook a listed note sits in: top-level in one spelling, under ``note_ext_info`` in the other."""
    ext = note.get("note_ext_info")
    return _text(note, "folder_name") or (_text(ext, "folder_name") if isinstance(ext, Mapping) else "")


def parse_notes_page(data: Mapping[str, object]) -> ImaNotesPage:
    """Decode one page of the notes listing and drop its deleted notes.

    Entries of which none can be read mean the wire shape changed rather than that the account holds no notes, so
    that raises instead of returning a page the inventory would take for "every note was deleted".
    """
    notes: list[ImaNote] = []
    unreadable = 0
    for raw in _entries(data, "note_book_list"):
        basic = _basic_info(raw)
        if _int(basic.get("status")) == 1:  # 1 = deleted
            continue
        note_id = _text(basic, "docid", "doc_id", "note_id")
        if not note_id:
            unreadable += 1
            continue
        notes.append(
            ImaNote(
                note_id=note_id,
                title=_text(basic, "title") or note_id,
                folder_name=_notebook_name(basic),
                modify_time=_int(basic.get("modify_time")) or 0,
            )
        )
    if unreadable and not notes:
        raise ImaPermanentError("ima returned notes in an unrecognized shape")
    return ImaNotesPage(notes=tuple(notes), next_cursor=_text(data, "next_cursor"), is_end=bool(data.get("is_end")))
