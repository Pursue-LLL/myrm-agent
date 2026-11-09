"""Bedrock authentication: an API key is a bearer token, anything else is signed with the AWS credential chain.

These tests replace the credential chain and the signature with doubles, so they run without botocore; the real
chain and the real signatures are checked in ``test_bedrock_sigv4``.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from dataclasses import dataclass, field

import pytest

from myrm_agent_harness.toolkits.llms.transport import bedrock_converse, bedrock_sigv4
from myrm_agent_harness.toolkits.llms.transport.bedrock_sigv4 import AwsCredentials
from myrm_agent_harness.toolkits.llms.transport.client import LLMTransport
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest, RequestSigner
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError, resolve_route

from .event_stream_bodies import converse_answer
from .provider_double import Provider, json_response

_MODEL = "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
_ARN = (
    "bedrock/converse/arn:aws:bedrock:eu-central-1:123456789012:inference-profile/eu.anthropic.claude-3-5-sonnet-v2:0"
)
_MESSAGES = [{"role": "user", "content": "hi"}]
_REGION_VARIABLES = ("AWS_REGION_NAME", "AWS_REGION", "AWS_DEFAULT_REGION")


@dataclass(frozen=True)
class _Frozen:
    access_key: str = "AKIDEXAMPLE"
    secret_key: str = "secret"
    token: str | None = None


@dataclass
class Chain:
    """Stands in for the credential chain and the signer: remembers who asked, from which thread, for which region."""

    profile_region: str | None = None
    lookups: list[int] = field(default_factory=list)  # the thread each lookup ran on
    signed_for: list[str] = field(default_factory=list)

    def load(self) -> AwsCredentials:
        self.lookups.append(threading.get_ident())
        return AwsCredentials(frozen=_Frozen(), region=self.profile_region)

    def signer(self, credentials: AwsCredentials, region: str) -> RequestSigner:
        self.signed_for.append(region)
        return lambda request: request.headers.update({"authorization": f"AWS4-HMAC-SHA256 region={region}"})


@pytest.fixture
def chain(monkeypatch: pytest.MonkeyPatch) -> Chain:
    double = Chain()
    monkeypatch.setattr(bedrock_converse, "load_credentials", double.load)
    monkeypatch.setattr(bedrock_converse, "request_signer", double.signer)
    for name in (*_REGION_VARIABLES, "AWS_BEARER_TOKEN_BEDROCK"):
        monkeypatch.delenv(name, raising=False)
    return double


def _prepare(model: str = _MODEL, api_key: str | None = None) -> PreparedRequest:
    return bedrock_converse.prepare(resolve_route(model, api_key=api_key), _MESSAGES, {})


class TestAuthentication:
    def test_an_api_key_is_a_bearer_token_and_the_credential_chain_is_not_consulted(self, chain: Chain) -> None:
        request = _prepare(api_key="bedrock-key")

        assert request.headers == {"Authorization": "Bearer bedrock-key"}
        assert request.signer is None
        assert chain.lookups == []

    def test_without_a_key_the_request_carries_a_signer_and_no_authorization_header(self, chain: Chain) -> None:
        request = _prepare()

        assert request.headers == {}
        assert request.signer is not None
        assert len(chain.lookups) == 1

    def test_a_signed_call_is_retried_like_any_other_model_call(self, chain: Chain) -> None:
        assert _prepare().retries == _prepare(api_key="k").retries == 2


class TestRegion:
    """The region of the endpoint, and of the signature, comes from the first source that names one."""

    def test_the_model_arn_names_the_region_before_any_variable(
        self, chain: Chain, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AWS_REGION", "us-east-1")

        request = _prepare(_ARN)

        assert request.url.startswith("https://bedrock-runtime.eu-central-1.amazonaws.com/")
        assert chain.signed_for == ["eu-central-1"]

    @pytest.mark.parametrize(
        ("variables", "expected"),
        [
            ({"AWS_REGION_NAME": "r-name", "AWS_REGION": "r-region", "AWS_DEFAULT_REGION": "r-default"}, "r-name"),
            ({"AWS_REGION": "r-region", "AWS_DEFAULT_REGION": "r-default"}, "r-region"),
            ({"AWS_DEFAULT_REGION": "r-default"}, "r-default"),
        ],
    )
    def test_the_variables_are_read_in_order(
        self, chain: Chain, monkeypatch: pytest.MonkeyPatch, variables: dict[str, str], expected: str
    ) -> None:
        chain.profile_region = "r-profile"
        for name, value in variables.items():
            monkeypatch.setenv(name, value)

        request = _prepare()

        assert request.url.startswith(f"https://bedrock-runtime.{expected}.amazonaws.com/")
        assert chain.signed_for == [expected]

    def test_the_region_of_the_aws_profile_comes_after_the_variables(self, chain: Chain) -> None:
        chain.profile_region = "ap-south-1"

        request = _prepare()

        assert request.url.startswith("https://bedrock-runtime.ap-south-1.amazonaws.com/")
        assert chain.signed_for == ["ap-south-1"]

    def test_with_no_source_the_default_region_is_used(self, chain: Chain) -> None:
        request = _prepare()

        assert request.url.startswith("https://bedrock-runtime.us-west-2.amazonaws.com/")
        assert chain.signed_for == ["us-west-2"]

    def test_an_api_key_call_never_reads_the_aws_profile(self, chain: Chain) -> None:
        chain.profile_region = "ap-south-1"

        assert _prepare(api_key="k").url.startswith("https://bedrock-runtime.us-west-2.amazonaws.com/")

    def test_a_custom_endpoint_keeps_its_host_and_is_signed_for_the_resolved_region(
        self, chain: Chain, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        route = resolve_route(_MODEL, api_base="https://gateway.example/bedrock")

        request = bedrock_converse.prepare(route, _MESSAGES, {})

        assert request.url.startswith("https://gateway.example/bedrock/model/")
        assert chain.signed_for == ["eu-west-1"]


class TestOffTheEventLoop:
    """Looking the credential chain up can read files and call a token service, so an async call never does it inline."""

    @staticmethod
    def _serve(provider: Provider) -> None:
        provider.serves(json_response(converse_answer({"text": "ok"})))

    def test_an_async_call_resolves_credentials_on_a_worker_thread(self, chain: Chain, provider: Provider) -> None:
        self._serve(provider)
        loop_threads: list[int] = []

        async def call() -> None:
            loop_threads.append(threading.get_ident())
            await LLMTransport().acompletion(model=_MODEL, messages=_MESSAGES)

        asyncio.run(call())

        assert len(chain.lookups) == 1
        assert chain.lookups[0] != loop_threads[0]
        assert provider.requests[0].headers["authorization"] == "AWS4-HMAC-SHA256 region=us-west-2"

    def test_an_async_call_with_a_key_needs_no_lookup(self, chain: Chain, provider: Provider) -> None:
        self._serve(provider)

        asyncio.run(LLMTransport().acompletion(model=_MODEL, messages=_MESSAGES, api_key="bedrock-key"))

        assert chain.lookups == []
        assert provider.requests[0].headers["authorization"] == "Bearer bedrock-key"

    def test_a_sync_call_resolves_credentials_inline(self, chain: Chain, provider: Provider) -> None:
        self._serve(provider)

        LLMTransport().completion(model=_MODEL, messages=_MESSAGES)

        assert chain.lookups == [threading.get_ident()]


class TestWithoutBotocore:
    def test_the_missing_package_is_named_with_the_way_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "botocore.exceptions", None)  # an import of it now fails

        with pytest.raises(UnsupportedProviderError, match=r"needs the botocore package.*Bedrock API key"):
            bedrock_sigv4.load_credentials()

    def test_an_api_key_call_never_imports_botocore(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("botocore", "botocore.exceptions", "botocore.session", "botocore.auth", "botocore.awsrequest"):
            monkeypatch.setitem(sys.modules, name, None)

        request = _prepare(api_key="bedrock-key")

        assert request.headers == {"Authorization": "Bearer bedrock-key"}
