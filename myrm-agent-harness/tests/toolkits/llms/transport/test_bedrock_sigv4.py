"""The AWS credential chain and the Signature Version 4 header as botocore produces them, checked without a network.

Needs botocore (extra ``bedrock``): the whole file is skipped where it is not installed. A signature is never compared
with a stored one (it carries the time); it is recomputed by ``sigv4_verifier``, which knows the algorithm and not
botocore.
"""

from __future__ import annotations

import shlex
import sys
from collections.abc import Mapping
from pathlib import Path

import httpx
import pytest

pytest.importorskip("botocore")

from myrm_agent_harness.toolkits.llms.transport import bedrock_sigv4
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
    bedrock_sigv4._sessions.clear()  # sessions outlive a call, so each test starts without one


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", _ACCESS_KEY)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", _SECRET_KEY)


class _Clock:
    """Stands in for the ``time`` module of ``bedrock_sigv4`` and moves only when a test says so."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(bedrock_sigv4, "time", fake)
    return fake


def _profile(access_key: str) -> str:
    return f"[default]\naws_access_key_id = {access_key}\naws_secret_access_key = {_SECRET_KEY}\n"


def _load_from_keys(monkeypatch: pytest.MonkeyPatch, number: int) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", f"AKID{number}")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", _SECRET_KEY)
    load_credentials()


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

    def test_credentials_that_appear_after_a_failed_lookup_are_used_at_once(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        credentials = tmp_path / "credentials"
        monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(credentials))
        with pytest.raises(UnsupportedProviderError):
            load_credentials()

        credentials.write_text(_profile("AKIDLATE"), encoding="utf-8")

        assert load_credentials().frozen.access_key == "AKIDLATE"

    def test_a_session_that_found_nothing_is_replaced_without_asking_the_chain_again(
        self, monkeypatch: pytest.MonkeyPatch, clock: _Clock
    ) -> None:
        """The cache lock must not be held while the chain is walked: that does disk and network I/O."""
        with pytest.raises(UnsupportedProviderError):
            load_credentials()
        (stale,) = (cached.session for cached in bedrock_sigv4._sessions.values())
        asked: list[str] = []
        monkeypatch.setattr(stale, "get_credentials", lambda: asked.append("the chain"))
        clock.now += 300

        with pytest.raises(UnsupportedProviderError):
            load_credentials()

        assert asked == []

    def test_keys_rewritten_in_the_shared_file_are_read_again_after_five_minutes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clock: _Clock
    ) -> None:
        credentials = tmp_path / "credentials"
        credentials.write_text(_profile("AKIDFIRST"), encoding="utf-8")
        monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(credentials))
        assert load_credentials().frozen.access_key == "AKIDFIRST"

        credentials.write_text(_profile("AKIDSECOND"), encoding="utf-8")
        clock.now += 299
        assert load_credentials().frozen.access_key == "AKIDFIRST"
        clock.now += 1
        assert load_credentials().frozen.access_key == "AKIDSECOND"

    @pytest.mark.skipif(sys.platform == "win32", reason="botocore splits credential_process by the Windows rules there")
    @pytest.mark.parametrize(
        ("reports_expiry", "runs"),
        [pytest.param(True, 1, id="renewed-by-botocore"), pytest.param(False, 4, id="read-again-every-window")],
    )
    def test_a_helper_process_is_run_again_only_when_it_reports_no_expiry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clock: _Clock, reports_expiry: bool, runs: int
    ) -> None:
        reply: dict[str, object] = {
            "Version": 1,
            "AccessKeyId": "AKIDHELPER",
            "SecretAccessKey": _SECRET_KEY,
            "SessionToken": "token",
        }
        if reports_expiry:
            reply["Expiration"] = "2099-01-01T00:00:00Z"
        log, helper = tmp_path / "runs", tmp_path / "helper.py"
        helper.write_text(
            f"import json, pathlib\npathlib.Path({str(log)!r}).open('a').write('x')\nprint(json.dumps({reply!r}))\n",
            encoding="utf-8",
        )
        (tmp_path / "config").write_text(
            f"[default]\ncredential_process = {shlex.quote(sys.executable)} {shlex.quote(str(helper))}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))

        for _ in range(4):
            assert load_credentials().frozen.access_key == "AKIDHELPER"
            clock.now += 300

        assert len(log.read_text(encoding="utf-8")) == runs

    def test_only_the_most_recent_sources_are_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for number in range(bedrock_sigv4._MAX_SESSIONS + 2):
            _load_from_keys(monkeypatch, number)

        assert len(bedrock_sigv4._sessions) == bedrock_sigv4._MAX_SESSIONS

    def test_a_source_used_again_outlasts_the_one_left_unused_longest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for number in range(bedrock_sigv4._MAX_SESSIONS):
            _load_from_keys(monkeypatch, number)
        _load_from_keys(monkeypatch, 0)
        _load_from_keys(monkeypatch, bedrock_sigv4._MAX_SESSIONS)

        at = bedrock_sigv4._CHAIN_ENV.index("AWS_ACCESS_KEY_ID")
        assert {key[at] for key in bedrock_sigv4._sessions} == {
            "AKID0",
            *(f"AKID{number}" for number in range(2, bedrock_sigv4._MAX_SESSIONS + 1)),
        }
