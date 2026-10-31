"""The enterprise network compatibility setting reaches the real client stacks.

[INPUT]
- infra.tls_compat::apply_global_tls_relaxation, create_httpx_client (POS: Enterprise TLS compatibility)
- toolkits.llms.core.llm::create_litellm_model (POS: The product's chat model factory)
- toolkits.llms.errors::classify_error, ErrorKind (POS: LLM error classification)
- tests.support.mcp_testkit.tls_pki::generate_inspection_chain (POS: Server chain shaped like a TLS-inspection proxy's)

[OUTPUT]
- Fails when the setting stops working for the product's chat model or for the harness's httpx clients: a chain
  issued by an inspection-proxy CA (``basicConstraints`` not critical) must be accepted once the setting is on and
  the environment names the CA, and rejected in every other combination.
- Fails when the setting weakens verification: an unknown CA, an expired certificate, a certificate for another host
  and a pinned CA that did not issue the certificate are all still rejected with the setting on.
- Fails when a rejection under the setting is no longer read as a rejected certificate.

[POS]
End-to-end drift guard for ``infra/tls_compat.py``. The unit tests prove the context policy; this proves that the
libraries the product talks to through (litellm's aiohttp transport, httpx) actually build their contexts through it,
against a loopback HTTPS listener whose chain strict OpenSSL verification rejects.
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import litellm
import pytest
from langchain_core.messages import HumanMessage
from litellm.llms.custom_httpx import http_handler as litellm_http_handler
from litellm.llms.custom_httpx.async_client_cleanup import close_litellm_async_clients

from myrm_agent_harness.infra.tls_compat import apply_global_tls_relaxation, create_httpx_client
from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from tests.support.mcp_testkit.tls_pki import InspectionChain, generate_inspection_chain
from tests.support.tls_loopback import CA_ENV_VARS, https_server, isolate_from_system_proxy, restore_standard_tls

_STACKS = ("httpx", "llm_factory")


async def _forget_cached_litellm_state() -> None:
    """litellm keeps one SSL context per CA file and every client it built, for the life of the process."""
    await close_litellm_async_clients()  # type: ignore[no-untyped-call]
    litellm_http_handler._ssl_context_cache.clear()
    litellm.in_memory_llm_clients_cache.flush_cache()  # type: ignore[no-untyped-call]


@pytest.fixture(autouse=True)
async def _pristine_tls(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Standard context builders, no TLS or proxy environment and no cached litellm clients, before and after."""
    restore_standard_tls(monkeypatch)
    isolate_from_system_proxy(monkeypatch)
    # The chat model writes its endpoint onto the litellm module on every call and leaves it there.
    monkeypatch.setattr(litellm, "api_base", None)
    monkeypatch.setattr(litellm, "api_key", None)
    await _forget_cached_litellm_state()
    # litellm builds its default context once, when it is imported, i.e. before any host reads the setting.
    litellm_http_handler.get_ssl_configuration()
    yield
    await _forget_cached_litellm_state()


@pytest.fixture
def chain(tmp_path: Path) -> InspectionChain:
    return generate_inspection_chain(tmp_path)


def _enterprise_mode(
    monkeypatch: pytest.MonkeyPatch, *, ca_env: str | None = None, ca_file: Path | None = None
) -> None:
    """What a host does at startup when the setting is on: set the toggle, name a CA, install the policy."""
    monkeypatch.setenv("MYRM_TLS_STRICT", "0")
    if ca_env is not None and ca_file is not None:
        monkeypatch.setenv(ca_env, str(ca_file))
    assert apply_global_tls_relaxation() is True


async def _call(stack: str, base_url: str) -> None:
    if stack == "httpx":
        async with create_httpx_client(timeout=10) as client:
            (await client.get(base_url)).raise_for_status()
        return
    model = create_litellm_model("openai/test-model", base_url=f"{base_url}/v1", api_key="test-key")
    reply = await model.ainvoke([HumanMessage(content="hi")])
    assert reply.content == "ok"


async def _assert_rejected_as_certificate(stack: str, base_url: str) -> None:
    with pytest.raises(Exception) as rejected:
        await _call(stack, base_url)
    assert classify_error(rejected.value) is ErrorKind.TLS_CERTIFICATE


@pytest.mark.parametrize("stack", _STACKS)
async def test_strict_verification_rejects_the_inspection_chain_by_default(stack: str, chain: InspectionChain) -> None:
    with https_server(chain) as url:
        await _assert_rejected_as_certificate(stack, url)


@pytest.mark.parametrize("stack", _STACKS)
async def test_the_setting_without_a_ca_does_not_trust_an_unknown_issuer(
    stack: str, chain: InspectionChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enterprise_mode(monkeypatch)

    with https_server(chain) as url:
        await _assert_rejected_as_certificate(stack, url)


@pytest.mark.parametrize("stack", _STACKS)
@pytest.mark.parametrize("ca_env", CA_ENV_VARS)
async def test_a_named_ca_without_the_setting_is_not_trusted(
    stack: str, ca_env: str, chain: InspectionChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ca_env, str(chain.ca_cert))
    assert apply_global_tls_relaxation() is False

    with https_server(chain) as url:
        await _assert_rejected_as_certificate(stack, url)


@pytest.mark.parametrize("stack", _STACKS)
@pytest.mark.parametrize("ca_env", CA_ENV_VARS)
async def test_the_setting_with_a_named_ca_accepts_the_inspection_chain(
    stack: str, ca_env: str, chain: InspectionChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enterprise_mode(monkeypatch, ca_env=ca_env, ca_file=chain.ca_cert)

    with https_server(chain) as url:
        await _call(stack, url)


@pytest.mark.parametrize("stack", _STACKS)
@pytest.mark.parametrize(
    ("server_names", "expired"),
    [(("127.0.0.1", "localhost"), True), (("other.example",), False)],
    ids=["expired", "other_host"],
)
async def test_the_setting_still_rejects_an_expired_certificate_and_one_for_another_host(
    stack: str,
    server_names: tuple[str, ...],
    expired: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flawed = generate_inspection_chain(tmp_path, server_names=server_names, expired=expired)
    _enterprise_mode(monkeypatch, ca_env="NODE_EXTRA_CA_CERTS", ca_file=flawed.ca_cert)

    with https_server(flawed) as url:
        await _assert_rejected_as_certificate(stack, url)


async def test_a_pinned_ca_keeps_exactly_that_trust_under_the_setting(
    chain: InspectionChain, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other = generate_inspection_chain(other_dir)
    _enterprise_mode(monkeypatch, ca_env="NODE_EXTRA_CA_CERTS", ca_file=chain.ca_cert)

    with https_server(chain) as url:
        async with httpx.AsyncClient(verify=ssl.create_default_context(cafile=str(other.ca_cert))) as pinned_elsewhere:
            with pytest.raises(httpx.ConnectError) as rejected:
                await pinned_elsewhere.get(url)
        assert classify_error(rejected.value) is ErrorKind.TLS_CERTIFICATE

        async with httpx.AsyncClient(verify=ssl.create_default_context(cafile=str(chain.ca_cert))) as pinned:
            assert (await pinned.get(url)).status_code == 200
