"""Retrieval embedding provisioning for PRIVATE Chrome E2E backends.

[SCOPE]
Memory APIs that build a MemoryManager need ``retrieval.embeddingConfig``. This makes
sure the backend has one that can actually embed, written through the same settings API
the WebUI uses. The config the stack seeded (the ``.env.test`` account) is kept once a
burst of one-text requests proves it works. Otherwise the ``.env.test`` accounts are
tried in order, the ``EMBEDDING_*`` account, the Voyage backup and then the Volcengine Ark
backup. When none can embed the block raises and names every refusal: a backend without a
working embedding silently degrades dense recall and fails every write that needs a vector,
so the run stops there. An account that cannot embed is one with an exhausted balance, a
rejected key, an unreachable endpoint, or a per-minute quota (a Voyage organisation without
a payment method answers the fourth request of a minute with HTTP 429).

The check is the product's own embedding call (settings entry, ``extract_retrieval_models``,
``aembed``), so a provider whose endpoint is built in (Voyage, Cohere, OpenAI) is reached
exactly as the product reaches it. It is synchronous: call it from a sync test.

Whatever the block overwrote is put back when it ends, including an absent config.

[USAGE]
    with configured_retrieval_embedding(get_e2e_api_url()):
        ...  # memory API calls that embed
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from myrm_agent_harness.toolkits.llms.transport.embeddings import aembed
from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError
from myrm_agent_harness.toolkits.llms.transport.http import aclose_clients

from app.core.channel_bridge.config_parsers.retrieval import extract_retrieval_models

_DEV_LIB = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))

from cdp_chat.support import fetch_config_value, put_config_value  # noqa: E402

from tests.support.test_secrets import TestSecrets, load_test_secrets  # noqa: E402

_PROBE_TIMEOUT_SEC = 15.0
# One more than the three requests a minute a Voyage organisation without a payment method is allowed.
_PROBE_BURST = 4
# The settings the block overwrites and puts back.
_OWNED_KEYS = ("embeddingApplied", "embeddingConfig")


async def _probe(config: Mapping[str, object]) -> str | None:
    embedding, _ = extract_retrieval_models({"embeddingApplied": True, "embeddingConfig": dict(config)})
    if embedding is None:
        return "incomplete config"
    attempts = (
        aembed(embedding.model, ["ping"], api_key=embedding.api_key, api_base=embedding.api_base) for _ in range(_PROBE_BURST)
    )
    try:
        outcomes = await asyncio.wait_for(asyncio.gather(*attempts, return_exceptions=True), _PROBE_TIMEOUT_SEC)
    except TimeoutError:
        return "TimeoutError"
    finally:
        await aclose_clients()
    for outcome in outcomes:
        if isinstance(outcome, LLMHTTPError):
            return f"HTTP {outcome.status_code}"
        if isinstance(outcome, BaseException):
            return type(outcome).__name__
    return None


def embedding_unusable_reason(config: Mapping[str, object]) -> str | None:
    """Why the account behind ``config`` cannot embed right now; ``None`` when a burst of one-text requests succeeds.

    Only the status or the error type is reported, never the response body.
    """
    return asyncio.run(_probe(config))


def _settings_form(model: str, api_key: str, api_base: str = "") -> dict[str, str]:
    """One ``.env.test`` account as the settings page stores it.

    A custom endpoint is an OpenAI-compatible provider; without one, ``provider/model`` is that provider's own endpoint
    and a bare model id is OpenAI's.
    """
    if api_base:
        return {"provider": "openai_compatible", "model": model, "apiKey": api_key, "apiBase": api_base}
    provider, separator, bare_model = model.partition("/")
    if not separator:
        return {"provider": "openai", "model": model, "apiKey": api_key}
    return {"provider": provider, "model": bare_model, "apiKey": api_key}


def _test_accounts(secrets: TestSecrets) -> list[tuple[str, dict[str, str]]]:
    """The ``.env.test`` accounts that can back dense recall, most preferred first."""
    accounts: list[tuple[str, dict[str, str]]] = []
    if (key := secrets.get("EMBEDDING_API_KEY")) and (model := secrets.get("EMBEDDING_MODEL")):
        accounts.append(("test account", _settings_form(model, key, secrets.get("EMBEDDING_BASE_URL"))))
    if (key := secrets.get("VOYAGE_API_KEY")) and (model := secrets.get("VOYAGE_EMBEDDING_MODEL")):
        accounts.append(("voyage backup", _settings_form(model, key)))
    # Ark is only reachable through its own endpoint: without one the key would be sent to a provider's default host.
    if (
        (key := secrets.get("ARK_EMBEDDING_API_KEY"))
        and (model := secrets.get("ARK_EMBEDDING_MODEL"))
        and (api_base := secrets.get("ARK_EMBEDDING_BASE_URL"))
    ):
        accounts.append(("ark backup", _settings_form(model, key, api_base)))
    return accounts


def _same_account(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return all(str(left.get(field) or "") == str(right.get(field) or "") for field in ("model", "apiKey", "apiBase"))


def _restore(base_url: str, original: Mapping[str, object]) -> None:
    current = fetch_config_value("retrieval", api_url=base_url)
    kept = {key: value for key, value in current.items() if key not in _OWNED_KEYS}
    put_config_value("retrieval", {**kept, **original}, api_url=base_url)


@contextmanager
def configured_retrieval_embedding(api_url: str) -> Iterator[None]:
    """Ensure a ``retrieval.embeddingConfig`` that can embed exists on ``api_url`` for the block's lifetime.

    Raises ``RuntimeError`` naming each refusal when no account can embed; the backend is left untouched then.
    """
    base_url = api_url.rstrip("/")
    retrieval = fetch_config_value("retrieval", api_url=base_url)
    existing = retrieval.get("embeddingConfig")
    refused: list[str] = []
    if existing:
        if (reason := embedding_unusable_reason(existing)) is None:
            yield
            return
        refused.append(f"seeded account: {reason}")

    chosen: dict[str, str] | None = None
    for label, account in _test_accounts(load_test_secrets()):
        if existing and _same_account(existing, account):
            continue  # The seeded account is this one, and it was just refused.
        if (reason := embedding_unusable_reason(account)) is None:
            print(f"E2E_EMBEDDING: {label} in use ({'; '.join(refused) or 'no seeded account'})", flush=True)
            chosen = account
            break
        refused.append(f"{label}: {reason}")

    if chosen is None:
        raise RuntimeError(
            f"No embedding account can embed ({'; '.join(refused) or 'none configured'}). "
            "Top up the quota or fix the EMBEDDING_*, VOYAGE_* and ARK_EMBEDDING_* accounts in .env.test."
        )

    original = {key: retrieval[key] for key in _OWNED_KEYS if key in retrieval}
    try:
        put_config_value("retrieval", {**retrieval, "embeddingApplied": True, "embeddingConfig": chosen}, api_url=base_url)
        yield
    finally:
        _restore(base_url, original)
