"""models.dev model catalog proxy.

[INPUT]
- myrm_agent_harness.infra.tls_compat::create_httpx_client (POS: httpx client whose TLS trust follows the enterprise network compatibility setting)
- app.core.utils.errors::external_service_error (POS: 502 error with a redacted, structured body)

[OUTPUT]
- router: ``GET /`` returns the models.dev catalog inside the standard success envelope.

[POS]
Server-side proxy for the public models.dev catalog that the model settings pages read. The request runs in this
process, so it validates certificates the way every other outbound request does, and the browser needs no cross-origin
access. The catalog is about 6 MB of JSON: it is cached as bytes for five minutes and spliced into the envelope without
being parsed, so a refresh costs neither a JSON parse nor a re-serialization.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from fastapi import APIRouter
from fastapi.responses import Response
from myrm_agent_harness.infra.tls_compat import create_httpx_client

from app.core.utils.errors import external_service_error

logger = logging.getLogger(__name__)

router = APIRouter()

_CATALOG_URL = "https://models.dev/api.json"
_FETCH_TIMEOUT_S = 10.0
_CACHE_TTL_S = 300.0
_ENVELOPE_HEAD = b'{"success":true,"code":0,"data":'
_ENVELOPE_TAIL = b"}"


async def _fetch_catalog_body() -> bytes:
    """Download the catalog and return it wrapped in the standard success envelope."""
    try:
        async with create_httpx_client(timeout=_FETCH_TIMEOUT_S, follow_redirects=True) as client:
            response = await client.get(_CATALOG_URL, headers={"Accept": "application/json"})
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        logger.warning("models.dev catalog request timed out: %s", exc)
        raise external_service_error("models.dev", "models.dev request timed out") from exc
    except httpx.HTTPError as exc:
        logger.warning("models.dev catalog request failed: %s", exc)
        raise external_service_error("models.dev", "Failed to fetch models.dev data") from exc

    body = response.content
    if not body[:64].lstrip().startswith(b"{"):
        logger.warning("models.dev catalog is not a JSON object (%d bytes)", len(body))
        raise external_service_error("models.dev", "models.dev returned an unexpected payload")
    return _ENVELOPE_HEAD + body + _ENVELOPE_TAIL


class _CatalogCache:
    """The enveloped catalog, downloaded at most once per TTL however many requests arrive together."""

    def __init__(self) -> None:
        self._body: bytes | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> bytes:
        async with self._lock:
            # A request that waited on the lock finds the download the first one made.
            if self._body is None or time.monotonic() >= self._expires_at:
                self._body = await _fetch_catalog_body()
                self._expires_at = time.monotonic() + _CACHE_TTL_S
            return self._body


_catalog_cache = _CatalogCache()


@router.get("")
async def get_models_dev_catalog() -> Response:
    """Return the models.dev catalog (provider id to provider and models) inside the standard success envelope."""
    return Response(content=await _catalog_cache.get(), media_type="application/json")
