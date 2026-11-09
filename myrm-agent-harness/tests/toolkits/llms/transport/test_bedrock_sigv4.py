"""The AWS credential chain and the Signature Version 4 header as botocore produces them, checked without a network.

Needs botocore, which the harness does not depend on: the whole file is skipped where it is not installed. A signature
is never compared with a stored one (it carries the time); it is recomputed by ``sigv4_verifier``, which knows the
algorithm and not botocore.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import httpx
import pytest

pytest.importorskip("botocore")

from myrm_agent_harness.toolkits.llms.transport.bedrock_sigv4 import load_credentials, request_signer
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError

from .sigv4_verifier import parse_authorization, signature_is_valid

_URL = "https://bedrock-runtime.us-east-1.amazonaws.com/model/anthropic.claude-3-5-sonnet-20241022-v2%3A0/converse"
_ACCESS_KEY, _SECRET_KEY = "AKIDTEST", "test-secret/key+value"
_SOURCES = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_ROLE_ARN",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
)


@pytest.fixture(autouse=True)
def _no_ambient_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The chain answers from what a test sets, never from the developer's own ``~/.aws`` or instance metadata."""
    for name in _SOURCES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", _ACCESS_KEY)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", _SECRET_KEY)


def _signed(
    *, region: str = "us-east-1", body: bytes = b'{"messages": []}', headers: Mapping[str, str] | None = None
) -> httpx.Request:
    request = httpx.Request("POST", _URL, content=body, headers={"content-type": "application/json", **(headers or {})})
    request_signer(load_credentials(), region)(request)
    return request


@pytest.mark.usefixtures("keys")
class TestSignature:
    def test_the_signature_is_the_one_the_algorithm_gives(self) -> None:
        request = _signed()

        signature = parse_authorization(request.headers["authorization"])
        assert (signature.access_key, signature.region, signature.service) == (_ACCESS_KEY, "us-east-1", "bedrock")
        assert signature.signed_headers == ("content-type", "host", "x-amz-date")
        assert signature_is_valid(request, _SECRET_KEY)
        assert "x-amz-security-token" not in request.headers

    def test_a_session_token_travels_with_the_request_and_is_signed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_SESSION_TOKEN", "session-token")

        request = _signed()

        assert request.headers["x-amz-security-token"] == "session-token"
        assert "x-amz-security-token" in parse_authorization(request.headers["authorization"]).signed_headers
        assert signature_is_valid(request, _SECRET_KEY)

    def test_the_signature_names_the_region_it_was_made_for(self) -> None:
        assert parse_authorization(_signed(region="eu-west-1").headers["authorization"]).region == "eu-west-1"

    def test_the_signature_covers_the_bytes_that_are_sent(self) -> None:
        signed = _signed(body=b'{"messages": []}')
        other_bytes = httpx.Request("POST", _URL, content=b'{"messages": [1]}', headers=signed.headers)

        assert signature_is_valid(signed, _SECRET_KEY)
        assert not signature_is_valid(other_bytes, _SECRET_KEY)

    def test_only_the_headers_the_wire_cannot_rewrite_are_signed(self) -> None:
        request = _signed(
            headers={"accept-encoding": "gzip", "x-amzn-bedrock-trace": "ENABLED", "user-agent": "agent/1"}
        )

        signed = parse_authorization(request.headers["authorization"]).signed_headers
        assert signed == ("content-type", "host", "x-amz-date", "x-amzn-bedrock-trace")
        assert signature_is_valid(request, _SECRET_KEY)


class TestCredentialChain:
    def test_the_chain_is_resolved_again_when_the_credential_variables_change(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDFIRST")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "first-secret")
        assert load_credentials().frozen.access_key == "AKIDFIRST"

        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDSECOND")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "second-secret")

        assert load_credentials().frozen.access_key == "AKIDSECOND"

    def test_a_profile_of_the_shared_files_gives_the_keys_and_the_region(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "credentials").write_text(
            f"[bedrock]\naws_access_key_id = {_ACCESS_KEY}\naws_secret_access_key = {_SECRET_KEY}\n", encoding="utf-8"
        )
        (tmp_path / "config").write_text("[profile bedrock]\nregion = ap-northeast-1\n", encoding="utf-8")
        monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
        monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
        monkeypatch.setenv("AWS_PROFILE", "bedrock")

        credentials = load_credentials()

        assert (credentials.frozen.access_key, credentials.frozen.secret_key) == (_ACCESS_KEY, _SECRET_KEY)
        assert credentials.region == "ap-northeast-1"

    def test_no_credentials_is_an_error_that_names_the_ways_to_provide_them(self) -> None:
        with pytest.raises(UnsupportedProviderError, match=r"No Bedrock credentials found.*AWS_BEARER_TOKEN_BEDROCK"):
            load_credentials()

    def test_an_unknown_profile_is_an_error_of_the_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_PROFILE", "missing")

        with pytest.raises(UnsupportedProviderError, match="AWS credentials could not be loaded"):
            load_credentials()
