"""Static guards: a provider that renders a reply into chunks delivers them through ``deliver_chunks`` alone.

Posting the chunks in a loop of its own leaves the first chunks to be sent again when a later one fails and
the message bus retries ``send()`` as a whole. Two checks hold the line. A provider file that renders a reply
calls the helper; and no provider file awaits inside a loop over the result of ``render`` or a ``split…`` helper,
which is what a second hand-written delivery path looks like, in a file that also calls the helper. The files
below render a reply but never post it chunk by chunk.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_PROVIDERS = Path(__file__).resolve().parents[3] / "app" / "channels" / "providers"

_NOT_POSTED_CHUNK_BY_CHUNK = {
    "email/channel.py": "the chunks are joined into the body of one mail",
    "voice_channel.py": "the chunks are joined into one text frame of the call",
    "wechat/ilink_channel.py": "all chunks go into the items of one request",
}

# The two ways a reply becomes several chunks: the renderer and the splitters it is built on.
_CHUNKING_CALLS = ("render", "split")


def _calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}


def _relative(path: Path) -> str:
    return path.relative_to(_PROVIDERS).as_posix()


def _is_chunking_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    callee = node.func
    name = callee.id if isinstance(callee, ast.Name) else callee.attr if isinstance(callee, ast.Attribute) else ""
    return name.lstrip("_").startswith(_CHUNKING_CALLS)


def _loops_awaiting_on_chunks(source: str) -> list[int]:
    """Lines of the loops that await while walking chunks: a ``render``/``split…`` call or a name bound to one."""
    tree = ast.parse(source)
    chunk_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_chunking_call(node.value):
            chunk_names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and node.value is not None and _is_chunking_call(node.value):
            if isinstance(node.target, ast.Name):
                chunk_names.add(node.target.id)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.For | ast.AsyncFor):
            continue
        walks_chunks = any(
            _is_chunking_call(part) or (isinstance(part, ast.Name) and part.id in chunk_names) for part in ast.walk(node.iter)
        )
        awaits = any(isinstance(part, ast.Await) for statement in node.body for part in ast.walk(statement))
        if walks_chunks and awaits:
            lines.append(node.lineno)
    return lines


_FILES = sorted(_PROVIDERS.rglob("*.py"))


@pytest.mark.parametrize("path", [p for p in _FILES if "render" in _calls(p)], ids=_relative)
def test_a_provider_that_renders_chunks_delivers_them_through_the_helper(path: Path) -> None:
    relative = _relative(path)
    delivers = "deliver_chunks" in _calls(path)

    if relative in _NOT_POSTED_CHUNK_BY_CHUNK:
        assert not delivers, f"{relative} uses deliver_chunks now: drop it from _NOT_POSTED_CHUNK_BY_CHUNK"
    else:
        assert delivers, f"{relative} renders a reply but does not post its chunks through deliver_chunks"


def test_every_exemption_still_names_a_file_that_renders() -> None:
    renders = {_relative(p) for p in _FILES if "render" in _calls(p)}

    assert set(_NOT_POSTED_CHUNK_BY_CHUNK) <= renders


def test_no_provider_posts_chunks_in_a_loop_of_its_own() -> None:
    offenders = {
        _relative(path): lines for path in _FILES if (lines := _loops_awaiting_on_chunks(path.read_text(encoding="utf-8")))
    }

    assert not offenders, f"post chunks through deliver_chunks, not a loop of your own (file: loop lines): {offenders}"


@pytest.mark.parametrize(
    "source",
    [
        "async def send(self, msg):\n    chunks = render(msg, style)\n    for chunk in chunks:\n        await self._post(chunk)\n",
        "async def send(self, msg):\n    chunks = render(msg, style)\n    for i, chunk in enumerate(chunks):\n        await self._post(chunk, i)\n",
        "async def send(self, msg):\n    chunks = render(msg, style)\n    await self._post(chunks[0])\n    for rest in chunks[1:]:\n        await self._post(rest)\n",
        "async def send(self, msg):\n    for part in split_markdown_rich(msg.content):\n        await self._post(part)\n",
        "async def send(self, msg):\n    chunks: list[str] = render(msg, style)\n    for chunk in chunks:\n        await self._post(chunk)\n",
        "async def send(self, msg):\n    chunks = self._split_text(msg.content)\n    for chunk in chunks:\n        await self._post(chunk)\n",
    ],
    ids=["plain", "enumerated", "tail", "splitter-in-the-loop-head", "annotated", "private-method"],
)
def test_the_loop_check_sees_a_hand_written_chunk_loop(source: str) -> None:
    assert _loops_awaiting_on_chunks(source)


@pytest.mark.parametrize(
    "source",
    [
        "async def send(self, msg):\n    chunks = render(msg, style)\n    await self._post('\\n'.join(chunks))\n",
        "async def send(self, msg):\n    chunks = render(msg, style)\n    items = []\n    for chunk in chunks:\n        items.append(chunk)\n    await self._post(items)\n",
        "async def send(self, msg):\n    for media in msg.media:\n        await self._upload(media)\n",
    ],
    ids=["joined", "collected", "attachments"],
)
def test_the_loop_check_leaves_other_loops_alone(source: str) -> None:
    assert not _loops_awaiting_on_chunks(source)
