"""Retrieval embedding provisioning for PRIVATE Chrome E2E backends.

[SCOPE]
Memory APIs that build a MemoryManager need ``retrieval.embeddingConfig``. This makes
sure the backend has one that can actually embed, written through the same settings API
the WebUI uses. A config already there is kept once a one-text request proves it works.
Otherwise the real embedding account from ``.env.test`` is preferred (what a user
configures), and a local OpenAI-compatible server is used when no account exists or the
account cannot embed (exhausted balance, rejected key, unreachable endpoint): such an
account silently degrades dense recall and fails every write that needs a vector, and the
stack seeds that same account into a fresh runtime. A dead config that was already on the
backend is put back when the block ends; the local server stays up for the whole block so
later embedding calls (for example approving a correction) still reach it.

[USAGE]
    with configured_retrieval_embedding(get_e2e_api_url()):
        ...  # memory API calls that embed
"""

from __future__ import annotations

import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import httpx

_DEV_LIB = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))

from cdp_chat.support import fetch_config_value, put_config_value  # noqa: E402

from tests.support.local_embedding_server import LocalEmbeddingServer  # noqa: E402
from tests.support.test_secrets import load_test_secrets  # noqa: E402

_PROBE_TIMEOUT_SEC = 15.0


def embedding_unusable_reason(config: Mapping[str, object]) -> str | None:
    """Why the account behind ``config`` cannot embed right now; ``None`` when a one-text request succeeds.

    Only the status or the error type is reported, never the response body.
    """
    api_base = str(config.get("apiBase") or "")
    if not api_base:
        return None  # The provider's default endpoint is unknown here, so there is nothing to probe.
    try:
        response = httpx.post(
            f"{api_base.rstrip('/')}/embeddings",
            json={"model": config.get("model"), "input": ["ping"]},
            headers={"Authorization": f"Bearer {config.get('apiKey')}"},
            timeout=_PROBE_TIMEOUT_SEC,
        )
    except httpx.HTTPError as exc:
        return type(exc).__name__
    return None if response.is_success else f"HTTP {response.status_code}"


@contextmanager
def configured_retrieval_embedding(api_url: str) -> Iterator[None]:
    """Ensure a ``retrieval.embeddingConfig`` that can embed exists on ``api_url`` for the block's lifetime."""
    base_url = api_url.rstrip("/")
    retrieval = fetch_config_value("retrieval", api_url=base_url)
    existing = retrieval.get("embeddingConfig")
    if existing and embedding_unusable_reason(existing) is None:
        yield
        return

    secrets = load_test_secrets()
    account: dict[str, str] | None = None
    if secrets.get("EMBEDDING_API_KEY"):
        account = {
            "provider": secrets.get("EMBEDDING_PROVIDER", "siliconflow"),
            "model": secrets.get("EMBEDDING_MODEL", "BAAI/bge-m3"),
            "apiKey": secrets.get("EMBEDDING_API_KEY"),
            "apiBase": secrets.get("EMBEDDING_BASE_URL"),
        }
    reason = "no EMBEDDING_API_KEY in .env.test" if account is None else embedding_unusable_reason(account)

    server: LocalEmbeddingServer | None = None
    try:
        if account is not None and reason is None:
            embedding_config = account
        else:
            print(f"E2E_EMBEDDING: local embedding server instead of the test account ({reason})", flush=True)
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
        if existing:
            restored = {**fetch_config_value("retrieval", api_url=base_url), "embeddingConfig": existing}
            put_config_value("retrieval", restored, api_url=base_url)
