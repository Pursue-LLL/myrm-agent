"""Converse messages: OpenAI-shaped chat messages become strictly alternating Converse turns.

[INPUT]
- core.thinking_blocks (POS: the signed reasoning blocks an assistant message carries)
- transport.capabilities (POS: claude_version — which models take an explicit cache point lifetime)

[OUTPUT]
- to_turns: the system blocks and the user / assistant turns of a conversation
- cache_point: the ``cachePoint`` blocks a ``cache_control`` marker stands for
- encode_tool_name / decode_tool_name: the lossless rewrite of a tool name into the alphabet Bedrock accepts
- Block / Turn: the shape of a content block and of one turn

[POS]
Message half of the Bedrock wire (``bedrock_converse`` builds the rest of the request). Converse demands alternating
turns and refuses a user turn that mixes text with tool results, so neighbours of one role are merged and the two
kinds are kept apart by a short assistant turn; a conversation that does not open or close with a user turn gets one;
blank text, which the API rejects, is dropped, and a tool that printed nothing still reports a short note. Tool names
are rewritten into ``[A-Za-z][A-Za-z0-9_-]*`` by an escape that ``decode_tool_name`` reverses, so a call comes back
under the name the agent registered. Only base64 images and documents can be sent: Converse takes bytes, not URLs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Final

from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY, coerce_thinking_blocks
from myrm_agent_harness.toolkits.llms.transport.capabilities import claude_version

logger = logging.getLogger(__name__)

Block = dict[str, object]
Turn = tuple[str, list[Block]]  # (role, content blocks)

_CONTINUE: Final = "Please continue."
_NO_OUTPUT: Final = "(no output)"
_DATA_URL: Final = re.compile(r"^data:(?P<media>[^;,]+);base64,(?P<data>.+)$", re.DOTALL)
_IMAGE_FORMATS: Final = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/gif": "gif",
    "image/webp": "webp",
}
_DOCUMENT_FORMATS: Final = {
    "application/pdf": "pdf",
    "text/csv": "csv",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/html": "html",
    "text/plain": "txt",
    "text/markdown": "md",
}
# The first Claude generation whose cache points take an explicit lifetime (``ttl``).
_LONG_CACHE_FROM: Final = (4, 5)
_INVALID_ID_CHARS: Final = re.compile(r"[^a-zA-Z0-9_-]")
_VALID_NAME: Final = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_ESCAPE_PREFIX: Final = "x__"
_ESCAPE: Final = re.compile(r"_([0-9a-f]+)_")


# --- tool names ------------------------------------------------------------------------------------------------


def encode_tool_name(name: str) -> str:
    """``name`` in Bedrock's alphabet: a valid name stays, any other is escaped character by character."""
    if _VALID_NAME.fullmatch(name) and not name.startswith(_ESCAPE_PREFIX):
        return name
    return _ESCAPE_PREFIX + re.sub(r"[^A-Za-z0-9-]", lambda m: f"_{ord(m[0]):x}_", name)


def decode_tool_name(name: str) -> str:
    if not name.startswith(_ESCAPE_PREFIX):
        return name
    return _ESCAPE.sub(lambda m: chr(int(m[1], 16)), name[len(_ESCAPE_PREFIX) :])


# --- content ---------------------------------------------------------------------------------------------------


def cache_point(marked: Mapping[str, object], model: str) -> list[Block]:
    """The cache point a message, part or tool carrying a ``cache_control`` marker stands for."""
    marker = marked.get("cache_control")
    if marker is None:
        return []
    point: Block = {"type": "default"}
    version = claude_version(model)
    if isinstance(marker, Mapping) and marker.get("ttl") in ("5m", "1h") and version and version >= _LONG_CACHE_FROM:
        point["ttl"] = marker["ttl"]
    return [{"cachePoint": point}]


def _image_block(part: Mapping[str, object]) -> Block | None:
    image = part.get("image_url")
    url = image.get("url") if isinstance(image, Mapping) else image
    match = _DATA_URL.match(url) if isinstance(url, str) else None
    fmt = _IMAGE_FORMATS.get(match["media"].lower()) if match else None
    if match is None or fmt is None:
        logger.warning("Dropping an image that is not base64 data of a supported type: Bedrock Converse takes bytes")
        return None
    return {"image": {"format": fmt, "source": {"bytes": match["data"]}}}


def _document_block(part: Mapping[str, object]) -> Block | None:
    file = part.get("file")
    data = file.get("file_data") if isinstance(file, Mapping) else None
    match = _DATA_URL.match(data) if isinstance(data, str) else None
    fmt = _DOCUMENT_FORMATS.get(match["media"].lower()) if match else None
    if match is None or fmt is None:
        logger.warning("Dropping a file that is not base64 data of a supported document type")
        return None
    # A document needs a name of its own within the request; its content digest names one file once.
    name = f"document-{hashlib.sha1(match['data'].encode(), usedforsecurity=False).hexdigest()[:12]}"
    return {"document": {"format": fmt, "name": name, "source": {"bytes": match["data"]}}}


def _part_block(part: Mapping[str, object]) -> Block | None:
    kind = part.get("type")
    if kind == "text":
        text = part.get("text")
        return {"text": text} if isinstance(text, str) and text.strip() else None
    if kind == "image_url":
        return _image_block(part)
    if kind == "file":
        return _document_block(part)
    logger.warning("Dropping content part of unsupported type %r for Bedrock Converse", kind)
    return None


def _parts(message: Mapping[str, object], model: str) -> list[Block]:
    """Text, image and document blocks of a message, each followed by the cache point it is marked with."""
    content = message.get("content")
    if isinstance(content, str):
        return [{"text": content}, *cache_point(message, model)] if content.strip() else []
    blocks: list[Block] = []
    for part in content if isinstance(content, list) else []:
        part = {"type": "text", "text": part} if isinstance(part, str) else part
        if isinstance(part, Mapping) and (block := _part_block(part)) is not None:
            blocks.append(block)
            blocks.extend(cache_point(part, model))
    return blocks


def _tool_id(raw: object) -> str:
    return _INVALID_ID_CHARS.sub("_", str(raw or "")) or "tool_use_id"


def _tool_use_blocks(tool_calls: object) -> list[Block]:
    blocks: list[Block] = []
    for call in tool_calls if isinstance(tool_calls, list) else []:
        function = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(function, Mapping):
            continue
        raw = function.get("arguments")
        try:
            arguments = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        except ValueError:
            arguments = {}
        use = {
            "toolUseId": _tool_id(call.get("id")),
            "name": encode_tool_name(str(function.get("name") or "")),
            "input": arguments if isinstance(arguments, dict) else {},
        }
        blocks.append({"toolUse": use})
    return blocks


def _thinking_blocks(message: Mapping[str, object]) -> list[Block]:
    """The reasoning the previous answer carried and the API will take back: signed text and redacted data."""
    blocks: list[Block] = []
    for block in coerce_thinking_blocks(message.get(THINKING_BLOCKS_KEY)):
        if block["type"] == "redacted_thinking":
            blocks.append({"reasoningContent": {"redactedContent": block["data"]}})
        else:
            text = {"text": block["thinking"], "signature": block["signature"]}
            blocks.append({"reasoningContent": {"reasoningText": text}})
    return blocks


def _tool_result(message: Mapping[str, object], model: str) -> list[Block]:
    """A ``toolResult`` block; its cache point sits beside it, not inside its content."""
    content = _parts(message, model)
    cache = [b for b in content if "cachePoint" in b][-1:] or cache_point(message, model)
    inner = [b for b in content if "cachePoint" not in b] or [{"text": _NO_OUTPUT}]
    return [{"toolResult": {"toolUseId": _tool_id(message.get("tool_call_id")), "content": inner}}, *cache]


def _unique(blocks: list[Block], key: str) -> list[Block]:
    """The first block per id: the API demands the ``toolUse`` / ``toolResult`` ids of a turn to be unique."""
    seen: set[object] = set()
    kept: list[Block] = []
    for block in blocks:
        inner = block.get(key)
        ident = inner.get("toolUseId") if isinstance(inner, Mapping) else None
        if ident is not None:
            if ident in seen:
                continue
            seen.add(ident)
        kept.append(block)
    return kept


# --- turns -----------------------------------------------------------------------------------------------------


def to_turns(messages: Sequence[Mapping[str, object]], model: str) -> tuple[list[Block], list[Turn]]:
    """(system blocks, strictly alternating user / assistant turns) for the Converse API."""
    system: list[Block] = []
    runs: list[tuple[str, str, list[Block]]] = []  # (role, kind, blocks): kind tells user text from tool results

    def push(role: str, kind: str, blocks: list[Block]) -> None:
        if not blocks:
            return
        if runs and runs[-1][1] == kind:
            runs[-1][2].extend(blocks)
        else:
            runs.append((role, kind, list(blocks)))

    for message in messages:
        role = message.get("role")
        if role in ("system", "developer"):
            system.extend(b for b in _parts(message, model) if "text" in b or "cachePoint" in b)
        elif role == "assistant":
            blocks = _thinking_blocks(message) + _parts(message, model) + _tool_use_blocks(message.get("tool_calls"))
            push("assistant", "assistant", blocks)
        elif role == "tool":
            push("user", "tool", _tool_result(message, model))
        elif role == "user":
            push("user", "user", _parts(message, model))
    turns: list[Turn] = []
    for role, _, blocks in runs:
        if turns and turns[-1][0] == role:  # user text next to tool results, in either order
            turns.append(("assistant", [{"text": _CONTINUE}]))
        turns.append((role, _unique(_unique(blocks, "toolUse"), "toolResult")))
    if not turns or turns[0][0] != "user":
        turns.insert(0, ("user", [{"text": _CONTINUE}]))
    if turns[-1][0] != "user":
        turns.append(("user", [{"text": _CONTINUE}]))
    return system, turns
