"""Token vocabularies shipped with the harness, so counting tokens never waits for a download.

``tiktoken`` fetches each vocabulary from a public CDN on first use. Behind a firewall, on a fresh container or in a
packaged desktop app with no network that fetch blocks or fails, and every count silently degrades to a character
estimate. The three vocabularies the harness and its embedding budgets use (``cl100k_base``, ``o200k_base``,
``p50k_base``) sit in ``_tiktoken_tables/`` under the file names ``tiktoken`` looks up in its cache directory; each is
checked against the hash ``tiktoken`` itself pins, so a damaged file is rejected, never trusted.

[INPUT]
- tiktoken (POS: BPE tokenizer whose cache directory is pointed at the bundled vocabularies)

[OUTPUT]
- get_encoding: the ``tiktoken`` encoding of a name, loaded from the bundled vocabularies
- encoding_for_model: the ``tiktoken`` encoding of a model name, loaded from the bundled vocabularies

[POS]
The one place that reaches ``tiktoken``. A host that names its own cache (``TIKTOKEN_CACHE_DIR`` or
``DATA_GYM_CACHE_DIR``) keeps it; a vocabulary missing from the bundle falls back to ``tiktoken``'s normal download.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tiktoken

_TABLES_DIR = Path(__file__).parent / "_tiktoken_tables"
_HOST_CACHE_VARS = ("TIKTOKEN_CACHE_DIR", "DATA_GYM_CACHE_DIR")


@cache
def _use_bundled_tables() -> None:
    """Point ``tiktoken``'s cache at the bundled vocabularies unless the host chose a cache of its own."""
    if _TABLES_DIR.is_dir() and not any(var in os.environ for var in _HOST_CACHE_VARS):
        os.environ["TIKTOKEN_CACHE_DIR"] = str(_TABLES_DIR)


def get_encoding(name: str) -> tiktoken.Encoding:
    """The encoding called *name* (``o200k_base`` ...); raises what ``tiktoken`` raises for an unknown name."""
    import tiktoken

    _use_bundled_tables()
    return tiktoken.get_encoding(name)


def encoding_for_model(model: str) -> tiktoken.Encoding:
    """The encoding *model* is tokenized with; raises ``KeyError`` for a model ``tiktoken`` does not know."""
    import tiktoken

    _use_bundled_tables()
    return tiktoken.encoding_for_model(model)
