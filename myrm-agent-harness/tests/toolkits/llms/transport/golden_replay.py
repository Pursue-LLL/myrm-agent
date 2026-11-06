"""Serves recorded provider replies from memory to the real chat adapter, so a recorded case replays through the whole call path.

[INPUT]
- transport.http (POS: the client factory and the retry pauses a replay replaces)
- adapters.chat_model.model::TransportChatModel (POS: the adapter a call goes through)

[OUTPUT]
- replaying(respond): context manager that answers every provider request with ``respond``; retry pauses are skipped
- model_for(wire, case, streaming): the adapter pointed at the case's own path of the in-memory provider
- case_of(request): the case a request belongs to

[POS]
Shared by the golden failure and answer replays. Each recorded case is addressed by the first path segment of the
base URL, so one shared HTTP client (the transport keeps one per event loop) serves every case.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.adapters.chat_model.model import TransportChatModel
from myrm_agent_harness.toolkits.llms.transport import http

_ORIGIN = "http://replay.test"
# Azure addresses its endpoint with a version; the recorded cases were served with this one.
_AZURE_API_VERSION = "2024-02-01"


def case_of(request: httpx.Request) -> str:
    return request.url.path.split("/")[1]


@contextlib.contextmanager
def replaying(respond: Callable[[httpx.Request], httpx.Response]) -> Iterator[None]:
    """Every provider request is answered by ``respond``; a retry waits no time, because the last attempt decides."""

    async def no_pause(seconds: float) -> None:
        return None

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(http, "_async_client", lambda proxy: httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        patch.setattr(http, "_apause", no_pause)
        patch.setattr(http, "_pause", lambda seconds: None)
        yield


def model_for(wire: str, case: str, *, streaming: bool = False) -> TransportChatModel:
    """The chat adapter for a recorded wire; a failed empty stream raises at once instead of waiting to retry."""
    options: dict[str, object] = {"api_version": _AZURE_API_VERSION} if wire == "azure" else {}
    if streaming:
        # Left unset otherwise: LangChain reads an explicit ``streaming=False`` as "never stream", even for ``astream``.
        options["streaming"] = True
    return TransportChatModel(
        model=f"{wire}/m",  # the prefix selects the protocol; the in-memory provider never reads the model id
        api_key="k",
        api_base=f"{_ORIGIN}/{case}",
        max_tokens=64,
        empty_retry_enabled=False,
        **options,
    )
