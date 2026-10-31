"""A rejected certificate is read as one failure across the real LLM client stack.

[INPUT]
- toolkits.llms.errors::classify_error, ErrorKind (POS: LLM error classification)
- toolkits.llms.errors.error_payload::MAX_CHAIN_DEPTH, walk_exception_chain (POS: The one reader of the provider's answer)
- agent.errors.diagnostics::LLMErrorDiagnostic (POS: LLM error diagnostic engine)
- tests.support.mcp_testkit.tls_pki::generate_tls_pki (POS: Throwaway PKI whose server certificate chains to a private CA)

[OUTPUT]
- Fails when a provider family's client layers word a rejected certificate in a shape the classifier or the
  diagnostics do not recognize, which sends the failure back to the retry, key-rotation or generic-connection paths.
- Fails when a plain-HTTP answer to an https request is taken for a certificate rejection and stops being retried.
- Fails when a client stack's exception chain grows past half of the bound the cause is read within, before one more
  client layer can push the rejected certificate out of reach.

[POS]
Drift guard for ``rejects_certificate``. Hand-built exception chains prove the logic; this test proves the chains
litellm actually raises, one per provider family, against a loopback listener whose certificate the client does not
trust (a private CA missing from the trust store, the situation of a TLS-inspecting corporate proxy). A listener that
answers plain HTTP pins the opposite side: a misconfigured scheme stays a transient transport failure.
"""

from __future__ import annotations

import socket
import ssl
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path

import litellm
import pytest

from myrm_agent_harness.agent.errors.diagnostics import LLMErrorDiagnostic
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.errors.error_payload import MAX_CHAIN_DEPTH, walk_exception_chain
from tests.support.mcp_testkit.tls_pki import generate_tls_pki

# One model per provider family whose client stack words a connection failure differently.
_PROVIDER_MODELS = (
    "openai/gpt-4o-mini",
    "anthropic/claude-3-5-haiku-latest",
    "gemini/gemini-2.0-flash",
    "ollama_chat/llama3",
    "deepseek/deepseek-chat",
)
_PROXY_VARIABLES = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")
_PLAIN_HTTP_ANSWER = b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n"


@dataclass
class _Listener:
    """A loopback endpoint that counts the connections it accepted."""

    port: int
    accepted: list[int] = field(default_factory=list)


@contextmanager
def _loopback_listener(handle: Callable[[socket.socket], None]) -> Iterator[_Listener]:
    """Run *handle* on every connection a loopback socket accepts, on a background thread."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    sock.settimeout(0.1)
    listener = _Listener(port=sock.getsockname()[1])
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            listener.accepted.append(1)
            with suppress(OSError), connection:
                connection.settimeout(1)
                handle(connection)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener
    finally:
        stop.set()
        thread.join(timeout=2)
        sock.close()


def _tls_handler(directory: Path) -> Callable[[socket.socket], None]:
    """Offer a certificate issued by a private CA; the client aborts the handshake once it has seen it."""
    pki = generate_tls_pki(directory)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(pki.server_cert, pki.server_key)

    def handle(connection: socket.socket) -> None:
        with context.wrap_socket(connection, server_side=True) as tls:
            tls.recv(1)

    return handle


def _plain_http_handler(connection: socket.socket) -> None:
    connection.recv(1024)
    connection.sendall(_PLAIN_HTTP_ANSWER)


@pytest.fixture(autouse=True)
def _direct_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in _PROXY_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    # The chat model writes its endpoint onto the litellm module on every call and leaves it there; a direct
    # ``litellm.acompletion`` of the next test would then reach that endpoint instead of its own listener.
    monkeypatch.setattr(litellm, "api_base", None)
    monkeypatch.setattr(litellm, "api_key", None)


@pytest.fixture
def untrusted_certificate_listener(tmp_path: Path) -> Iterator[_Listener]:
    with _loopback_listener(_tls_handler(tmp_path)) as listener:
        yield listener


@pytest.fixture
def plain_http_listener() -> Iterator[_Listener]:
    with _loopback_listener(_plain_http_handler) as listener:
        yield listener


async def _failure_of_https_call(model: str, listener: _Listener) -> Exception:
    try:
        await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            api_base=f"https://127.0.0.1:{listener.port}",
            api_key="test-key",
            num_retries=0,
            ssl_verify=True,
            timeout=10,
        )
    except Exception as exc:
        # Each provider stack raises its own class. The request reached the local listener, so the failure is
        # the connection under test and not a stray one.
        assert listener.accepted
        return exc
    raise AssertionError("the https call to the local listener must fail")


@pytest.mark.parametrize("model", _PROVIDER_MODELS)
async def test_every_provider_family_reads_a_rejected_certificate_the_same_way(
    model: str, untrusted_certificate_listener: _Listener
) -> None:
    failure = await _failure_of_https_call(model, untrusted_certificate_listener)

    assert classify_error(failure) is ErrorKind.TLS_CERTIFICATE
    assert LLMErrorDiagnostic.diagnose(failure, None, locale="en").error_type == "tls_certificate"
    assert len(walk_exception_chain(failure)) <= MAX_CHAIN_DEPTH // 2


@pytest.mark.parametrize("model", _PROVIDER_MODELS)
async def test_plain_http_answer_to_https_call_is_not_taken_for_a_rejected_certificate(
    model: str, plain_http_listener: _Listener
) -> None:
    failure = await _failure_of_https_call(model, plain_http_listener)

    assert classify_error(failure) is ErrorKind.TIMEOUT
    assert LLMErrorDiagnostic.diagnose(failure, None, locale="en").error_type != "tls_certificate"
