"""Retrieval embedding provisioning for PRIVATE Chrome E2E backends.

[SCOPE]
A PRIVATE backend starts from an empty database, so memory APIs that build a
MemoryManager need ``retrieval.embeddingConfig`` first. This writes it through the
same settings API the WebUI uses. The real embedding account from ``.env.test`` is
preferred (what a user configures); a local OpenAI-compatible server is used only
when no test account exists, and stays up for the caller's whole block so later
embedding calls (for example approving a correction) still reach it.

[USAGE]
    with configured_retrieval_embedding(get_e2e_api_url()):
        ...  # memory API calls that embed
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_DEV_LIB = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))

from cdp_chat.support import fetch_config_value, put_config_value  # noqa: E402

from tests.support.local_embedding_server import LocalEmbeddingServer  # noqa: E402
from tests.support.test_secrets import load_test_secrets  # noqa: E402


@contextmanager
def configured_retrieval_embedding(api_url: str) -> Iterator[None]:
    """Ensure ``retrieval.embeddingConfig`` exists on ``api_url`` for the block's lifetime."""
    base_url = api_url.rstrip("/")
    retrieval = fetch_config_value("retrieval", api_url=base_url)
    if retrieval.get("embeddingConfig"):
        yield
        return

    secrets = load_test_secrets()
    server: LocalEmbeddingServer | None = None
    try:
        if secrets.get("EMBEDDING_API_KEY"):
            embedding_config = {
                "provider": secrets.get("EMBEDDING_PROVIDER", "siliconflow"),
                "model": secrets.get("EMBEDDING_MODEL", "BAAI/bge-m3"),
                "apiKey": secrets.get("EMBEDDING_API_KEY"),
                "apiBase": secrets.get("EMBEDDING_BASE_URL"),
            }
        else:
            server = LocalEmbeddingServer(port=0).start()
            embedding_config = {
                "provider": "openai_compatible",
                "model": "BAAI/bge-m3",
                "apiKey": "test-key",
                "apiBase": server.base_url,
            }
        put_config_value(
            "retrieval",
            {**retrieval, "embeddingApplied": True, "embeddingConfig": embedding_config},
            api_url=base_url,
        )
        yield
    finally:
        if server is not None:
            server.stop()
