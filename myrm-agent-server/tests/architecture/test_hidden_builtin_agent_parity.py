"""Architecture test: the web client hides the same built-in agent ids as the server.

The server filters hidden presets out of every agent list, and the client keeps them out of its picker and sends a
message that names one to the general agent. A set that differs between the two sides lets a retired preset reappear
in one of them.
"""

from __future__ import annotations

import re
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_PRODUCT_SURFACE = _SERVER_ROOT.parent / "myrm-agent-frontend" / "src" / "lib" / "product-surface.ts"

_HIDDEN_SET_PATTERN = re.compile(r"HIDDEN_BUILTIN_AGENT_IDS\s*=\s*new Set\(\[(?P<ids>[^\]]*)\]\)")
_ID_PATTERN = re.compile(r"'([^']+)'")


def _parse_frontend_hidden_ids(source: str) -> set[str]:
    match = _HIDDEN_SET_PATTERN.search(source)
    assert match, "HIDDEN_BUILTIN_AGENT_IDS Set literal not found in product-surface.ts"
    return set(_ID_PATTERN.findall(match.group("ids")))


def test_frontend_hides_the_same_builtin_agents_as_the_server() -> None:
    from app.services.features.product_surface import HIDDEN_BUILTIN_AGENT_IDS

    assert _FRONTEND_PRODUCT_SURFACE.is_file(), f"Missing frontend product surface file: {_FRONTEND_PRODUCT_SURFACE}"
    frontend_ids = _parse_frontend_hidden_ids(_FRONTEND_PRODUCT_SURFACE.read_text(encoding="utf-8"))
    server_ids = set(HIDDEN_BUILTIN_AGENT_IDS)

    assert frontend_ids == server_ids, (
        "Hidden built-in agent ids differ between app/services/features/product_surface.py and "
        "myrm-agent-frontend/src/lib/product-surface.ts: "
        f"only on the server {sorted(server_ids - frontend_ids)}, only in the client {sorted(frontend_ids - server_ids)}"
    )


def test_set_literal_parser_reads_a_wrapped_set() -> None:
    source = "export const HIDDEN_BUILTIN_AGENT_IDS = new Set([\n  'builtin-a',\n  'builtin-b',\n]);\n"

    assert _parse_frontend_hidden_ids(source) == {"builtin-a", "builtin-b"}
