"""A real chat model for live tests, with an HTTP client that belongs to the calling test.

[INPUT]
- langchain_openai::ChatOpenAI (POS: the OpenAI-compatible chat model every live test talks to a real provider with)
- httpx::AsyncClient (POS: the async HTTP client handed to ChatOpenAI)

[OUTPUT]
- live_chat_model: async context manager yielding a ChatOpenAI whose HTTP client is opened and closed with the block

[POS]
Server pytest-only helper for every test that calls a real model. langchain-openai shares one cached async HTTP client
per process, and its pooled connections stay bound to the event loop of the test that opened them, so the next test, on a
new loop, fails with ``Event loop is closed``. A client opened inside the test and closed with it never outlives its loop.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from langchain_openai import ChatOpenAI
from pydantic import SecretStr


@asynccontextmanager
async def live_chat_model(
    *,
    model: str,
    api_key: str | None,
    base_url: str | None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
) -> AsyncIterator[ChatOpenAI]:
    """Yield a ChatOpenAI for ``model`` on the event loop of the test that enters the block."""
    async with httpx.AsyncClient() as http_async_client:
        yield ChatOpenAI(
            model=model,
            api_key=SecretStr(api_key) if api_key is not None else None,
            base_url=base_url,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            timeout=timeout,
            http_async_client=http_async_client,
        )
