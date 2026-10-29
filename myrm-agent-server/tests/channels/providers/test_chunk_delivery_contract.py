"""Static guard: a provider file that renders a reply into chunks calls ``deliver_chunks``.

Posting the chunks in a loop of its own leaves the first chunks to be sent again when a later one fails and
the message bus retries ``send()`` as a whole. The check only proves that the file calls the helper: a second
hand-written loop in the same file passes it, so the behaviour of each path is pinned by the provider's own
delivery tests. The files below render a reply but never post it chunk by chunk.
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


def _calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}


def _relative(path: Path) -> str:
    return path.relative_to(_PROVIDERS).as_posix()


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
