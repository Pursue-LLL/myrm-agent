"""``bounded_get`` keeps what a transfer sends up to the bound and ends the transfer there.

The stand-in for ``AsyncFetcher.get`` feeds the write callback the way libcurl does and raises the write error curl_cffi
raises once the callback answers with its abort code, so these tests pin the sink's accounting and the error handling.
``test_bounded_get_loopback.py`` pins the behaviour of the real libraries.
"""

from __future__ import annotations

import sys
import tracemalloc
from collections.abc import Awaitable, Callable, Iterable
from types import ModuleType, SimpleNamespace

import pytest

from myrm_agent_harness.toolkits.web_fetch.fetchers.bounded_get import MAX_TRANSFER_BYTES, bounded_get

curl = pytest.importorskip("curl_cffi.curl")
curl_requests = pytest.importorskip("curl_cffi.requests")

GetFn = Callable[..., Awaitable[object]]

URL = "https://example.org/page"
MIB = b"x" * 1_048_576


class _Transfer:
    """A stand-in for ``AsyncFetcher.get`` that streams ``chunks`` into the write callback."""

    def __init__(
        self,
        chunks: Iterable[bytes],
        *,
        response: object | None = None,
        interrupted: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self._chunks = chunks
        self._response = response
        self._interrupted = interrupted
        self._error = error
        self.fed = 0
        self.kwargs: dict[str, object] = {}

    async def get(self, url: str, *, content_callback: Callable[[bytes], int], **kwargs: object) -> object:
        self.kwargs = kwargs
        for chunk in self._chunks:
            self.fed += len(chunk)
            if content_callback(chunk) == curl.CURL_WRITEFUNC_ERROR:
                raise curl_requests.RequestsError("Failed to perform, curl: (23)", code=23, response=self._interrupted)
        if self._error is not None:
            raise self._error
        return self._response


def _scrapling_response(status: int = 200) -> SimpleNamespace:
    return SimpleNamespace(status=status, headers={"content-type": "text/html"}, url=URL, encoding="utf-8")


def _curl_response(status: int = 200) -> SimpleNamespace:
    return SimpleNamespace(
        status_code=status, headers={"content-type": "text/html", "x-probe": "kept"}, url=URL, encoding="latin-1"
    )


@pytest.fixture
def install_get(monkeypatch: pytest.MonkeyPatch) -> Callable[[GetFn], None]:
    def install(get: GetFn) -> None:
        fetchers = ModuleType("scrapling.fetchers")
        fetchers.AsyncFetcher = type("AsyncFetcher", (), {"get": staticmethod(get)})
        scrapling = ModuleType("scrapling")
        scrapling.fetchers = fetchers
        monkeypatch.setitem(sys.modules, "scrapling", scrapling)
        monkeypatch.setitem(sys.modules, "scrapling.fetchers", fetchers)

    return install


async def test_body_under_the_bound_is_kept_whole_with_the_response_fields(
    install_get: Callable[[GetFn], None],
) -> None:
    transfer = _Transfer([b"<html>", b"</html>"], response=_scrapling_response(status=203))
    install_get(transfer.get)

    fetched = await bounded_get(URL, {"timeout": 10})

    assert fetched.body == b"<html></html>"
    assert (fetched.status, fetched.headers, fetched.url, fetched.encoding) == (
        203,
        {"content-type": "text/html"},
        URL,
        "utf-8",
    )


async def test_request_is_attempted_once_and_the_caller_parameters_are_forwarded(
    install_get: Callable[[GetFn], None],
) -> None:
    transfer = _Transfer([b"ok"], response=_scrapling_response())
    install_get(transfer.get)
    request = {"timeout": 10, "follow_redirects": False, "retries": 3}

    await bounded_get(URL, request)

    assert transfer.kwargs == {"timeout": 10, "follow_redirects": False, "retries": 1}
    assert request["retries"] == 3


async def test_body_over_the_bound_ends_the_transfer_one_byte_over(install_get: Callable[[GetFn], None]) -> None:
    transfer = _Transfer((MIB for _ in range(25)), interrupted=_curl_response(status=206))
    install_get(transfer.get)

    fetched = await bounded_get(URL, {})

    assert len(fetched.body) == MAX_TRANSFER_BYTES + 1
    assert transfer.fed == 21 * len(MIB)
    assert (fetched.status, fetched.headers["x-probe"], fetched.url, fetched.encoding) == (206, "kept", URL, "latin-1")


async def test_a_full_body_is_held_once_when_the_transfer_ends(install_get: Callable[[GetFn], None]) -> None:
    chunk = b"x" * 16_384
    chunks = (chunk for _ in range(MAX_TRANSFER_BYTES // len(chunk) + 2))
    install_get(_Transfer(chunks, interrupted=_curl_response()).get)

    tracemalloc.start()
    try:
        fetched = await bounded_get(URL, {})
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert len(fetched.body) == MAX_TRANSFER_BYTES + 1
    # Handing the body over as a copy of a bytearray would put the peak at about twice the bound.
    assert peak < 1.5 * MAX_TRANSFER_BYTES


@pytest.mark.parametrize(("extra_bytes", "expected"), [(0, MAX_TRANSFER_BYTES), (1, MAX_TRANSFER_BYTES + 1)])
async def test_a_body_at_the_bound_is_told_from_one_byte_over(
    install_get: Callable[[GetFn], None], extra_bytes: int, expected: int
) -> None:
    chunks = [MIB] * 20 + [b"x" * extra_bytes]
    transfer = _Transfer(chunks, response=_scrapling_response(), interrupted=_curl_response())
    install_get(transfer.get)

    fetched = await bounded_get(URL, {})

    assert len(fetched.body) == expected


@pytest.mark.parametrize(
    "failure",
    [
        curl_requests.RequestsError("Operation timed out", code=28),
        curl_requests.RequestsError("Transfer closed early", code=18, response=_curl_response()),
        ValueError("not a transfer error"),
    ],
    ids=["transfer-error", "transfer-error-after-the-headers", "other-error"],
)
async def test_failure_before_the_bound_is_raised(install_get: Callable[[GetFn], None], failure: Exception) -> None:
    install_get(_Transfer([b"partial"], error=failure).get)

    with pytest.raises(type(failure)) as raised:
        await bounded_get(URL, {})

    assert raised.value is failure


async def test_write_error_without_a_response_is_raised(install_get: Callable[[GetFn], None]) -> None:
    install_get(_Transfer((MIB for _ in range(25)), interrupted=None).get)

    with pytest.raises(curl_requests.RequestsError):
        await bounded_get(URL, {})
