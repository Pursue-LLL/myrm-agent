"""Records which credentials, endpoint and signature leave the process for Azure, Anthropic and Bedrock calls.

[INPUT]
- core.llm::create_chat_model (POS: the production model factory)
- golden_canned::canned_answer (POS: a valid answer in the protocol each request addresses)
- golden_matrix::JSON_SCHEMA (POS: the structured-output request of the structured scenarios)
- sigv4_verifier (POS: independent check of an AWS Signature Version 4)
- httpx (POS: patched ``send`` that every client library ends in)

[OUTPUT]
- capture_credentials: {case: verdict} for the matrix; a verdict is a flat mapping of named facts about the request
- ``python -m tests.toolkits.llms.transport.golden_credentials OUT.json [key=value ...]``: records the matrix

[POS]
Library-agnostic capture of how a call authenticates and where it goes, through the production factory with an
environment that holds only what the case sets. A fact is one thing a provider (or an attacker reading the request)
can see: the URL and query, each credential header with the secret replaced by its name, the secrets that reached the
body or the URL, and for a signed Bedrock request the scope, the signed headers and whether the signature is valid by
an independent computation. The committed ``golden_credentials_baseline.json`` was recorded by running this module
against the baseline client library (litellm 1.97.0); ``test_golden_credentials`` replays the matrix on the transport.
Nothing here imports a client library, so the same module runs against either stack.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.core.llm import create_chat_model

from .golden_canned import canned_answer
from .golden_compare import Verdict
from .golden_matrix import JSON_SCHEMA
from .sigv4_verifier import parse_authorization, signature_is_valid

_SECRETS = {
    "api_key": "sk-golden-key",
    "env_key": "golden-env-key",
    "ad_token": "golden-ad-token",
    "oauth_token": "sk-ant-oat01-golden-oauth",
    "access_key": "AKIDGOLDEN",
    "secret_key": "golden/secret+key",
    "session_token": "golden-session-token",
}
_BASE = "http://golden.invalid"
_AZURE, _CLAUDE = "azure/gpt-4o", "anthropic/claude-sonnet-4-5"
_BEDROCK = "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
# The ``converse/`` prefix names the operation, so no stack has to infer it from an ARN that says nothing of the model.
_BEDROCK_ARN = (
    "bedrock/converse/arn:aws:bedrock:eu-central-1:123456789012:inference-profile/eu.anthropic.claude-3-5-sonnet-v2:0"
)
_AWS_ENV = {
    "AWS_ACCESS_KEY_ID": _SECRETS["access_key"],
    "AWS_SECRET_ACCESS_KEY": _SECRETS["secret_key"],
    "AWS_REGION": "us-east-1",
}
# What the credential chain reads from files: the keys and the region of the default profile.
_CREDENTIALS_FILE = (
    f"[default]\naws_access_key_id = {_SECRETS['access_key']}\naws_secret_access_key = {_SECRETS['secret_key']}\n"
)
_CONFIG_FILE = "[default]\nregion = ap-south-1\n"
_ENV_PREFIXES = ("AWS_", "AZURE", "ANTHROPIC", "OPENAI")
_PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy")
_CREDENTIAL_HEADERS = frozenset({"api-key", "authorization", "x-api-key", "x-goog-api-key"})
_SHOWN_PREFIXES = ("anthropic-", "x-amz-")


@dataclass(frozen=True, slots=True)
class Scenario:
    model: str
    env: Mapping[str, str] = field(default_factory=dict)
    kwargs: Mapping[str, object] = field(default_factory=dict)
    stream: bool = False
    structured: bool = False
    files: Mapping[str, str] = field(default_factory=dict)  # AWS shared files the case writes, by file name


def _key(**kwargs: object) -> dict[str, object]:
    return {"api_key": _SECRETS["api_key"], **kwargs}


def _version(version: str) -> dict[str, object]:
    return {"model_kwargs": {"api_version": version}}


_OAUTH_KEY = {"api_key": _SECRETS["oauth_token"]}
_BETA = {"model_kwargs": {"extra_headers": {"anthropic-beta": "context-1m-2025-08-07"}}}

SCENARIOS: dict[str, Scenario] = {
    "azure|key_explicit": Scenario(_AZURE, kwargs=_key(base_url=_BASE)),
    "azure|key_env": Scenario(_AZURE, {"AZURE_API_KEY": _SECRETS["env_key"]}, {"base_url": _BASE}),
    "azure|key_env_openai_name": Scenario(_AZURE, {"AZURE_OPENAI_API_KEY": _SECRETS["env_key"]}, {"base_url": _BASE}),
    "azure|base_env": Scenario(_AZURE, {"AZURE_API_BASE": _BASE, "AZURE_API_KEY": _SECRETS["env_key"]}),
    "azure|endpoint_env": Scenario(_AZURE, {"AZURE_OPENAI_ENDPOINT": _BASE, "AZURE_API_KEY": _SECRETS["env_key"]}),
    "azure|version_env": Scenario(_AZURE, {"AZURE_API_VERSION": "2099-01-01"}, _key(base_url=_BASE)),
    "azure|version_explicit": Scenario(_AZURE, kwargs=_key(base_url=_BASE, **_version("2024-10-21"))),
    "azure|version_explicit_over_env": Scenario(
        _AZURE, {"AZURE_API_VERSION": "2099-01-01"}, _key(base_url=_BASE, **_version("2024-10-21"))
    ),
    "azure|ad_token": Scenario(
        _AZURE, kwargs={"base_url": _BASE, "model_kwargs": {"azure_ad_token": _SECRETS["ad_token"]}}
    ),
    "azure|ad_token_and_key": Scenario(
        _AZURE, kwargs=_key(base_url=_BASE, model_kwargs={"azure_ad_token": _SECRETS["ad_token"]})
    ),
    "azure|stream": Scenario(_AZURE, kwargs=_key(base_url=_BASE), stream=True),
    "azure_responses|default": Scenario(_AZURE, kwargs=_key(base_url=_BASE, wire_protocol="responses")),
    "azure_responses|version_env": Scenario(
        _AZURE, {"AZURE_API_VERSION": "2099-01-01"}, _key(base_url=_BASE, wire_protocol="responses")
    ),
    "azure_responses|version_explicit": Scenario(
        _AZURE, kwargs=_key(base_url=_BASE, wire_protocol="responses", **_version("2025-03-01-preview"))
    ),
    "anthropic|key_official": Scenario(_CLAUDE, kwargs=_key()),
    "anthropic|key_gateway": Scenario(_CLAUDE, kwargs=_key(base_url=_BASE)),
    "anthropic|key_env": Scenario(_CLAUDE, {"ANTHROPIC_API_KEY": _SECRETS["env_key"]}),
    "anthropic|key_caller_beta": Scenario(_CLAUDE, kwargs=_key(**_BETA)),
    "anthropic|key_structured": Scenario(_CLAUDE, kwargs=_key(), structured=True),
    "anthropic|oauth_official": Scenario(_CLAUDE, kwargs=_OAUTH_KEY),
    "anthropic|oauth_gateway": Scenario(_CLAUDE, kwargs={**_OAUTH_KEY, "base_url": _BASE}),
    "anthropic|oauth_env": Scenario(_CLAUDE, {"ANTHROPIC_API_KEY": _SECRETS["oauth_token"]}),
    "anthropic|oauth_caller_beta": Scenario(_CLAUDE, kwargs={**_OAUTH_KEY, **_BETA}),
    "anthropic|oauth_structured": Scenario(_CLAUDE, kwargs=_OAUTH_KEY, structured=True),
    "anthropic|oauth_stream": Scenario(_CLAUDE, kwargs=_OAUTH_KEY, stream=True),
    "bedrock|bearer_key": Scenario(_BEDROCK, {"AWS_REGION": "us-east-1"}, _key()),
    "bedrock|bearer_env": Scenario(
        _BEDROCK, {"AWS_BEARER_TOKEN_BEDROCK": _SECRETS["env_key"], "AWS_REGION": "us-east-1"}
    ),
    "bedrock|bearer_wins_over_aws_keys": Scenario(_BEDROCK, _AWS_ENV, _key()),
    "bedrock|sigv4_env": Scenario(_BEDROCK, _AWS_ENV),
    "bedrock|sigv4_session_token": Scenario(
        _BEDROCK, {**_AWS_ENV, "AWS_SESSION_TOKEN": _SECRETS["session_token"], "AWS_REGION_NAME": "eu-west-1"}
    ),
    "bedrock|sigv4_arn_region": Scenario(_BEDROCK_ARN, _AWS_ENV),
    "bedrock|sigv4_stream": Scenario(_BEDROCK, _AWS_ENV, stream=True),
    "bedrock|sigv4_custom_base": Scenario(_BEDROCK, _AWS_ENV, {"base_url": _BASE}),
    "bedrock|sigv4_default_region": Scenario(_BEDROCK, {k: v for k, v in _AWS_ENV.items() if k != "AWS_REGION"}),
    "bedrock|sigv4_region_variables": Scenario(
        _BEDROCK, {**_AWS_ENV, "AWS_DEFAULT_REGION": "ap-northeast-1", "AWS_REGION": "us-east-1"}
    ),
    "bedrock|sigv4_credentials_file": Scenario(
        _BEDROCK, files={"credentials": _CREDENTIALS_FILE, "config": _CONFIG_FILE}
    ),
    "bedrock|sigv4_no_credentials": Scenario(_BEDROCK, {"AWS_REGION": "us-east-1"}),
}


def _labelled(text: str) -> str:
    for name, value in _SECRETS.items():
        text = text.replace(value, f"<{name}>")
    return text


def _facts(request: httpx.Request) -> Verdict:
    """What one request shows: endpoint, credential headers by secret name, secrets in the body or URL, signature."""
    split, body = urlsplit(str(request.url)), request.content.decode("utf-8", "replace")
    facts: Verdict = {
        "url": f"{split.scheme}://{split.netloc}{split.path}",
        "query": split.query,
        "secrets_in_body": sorted(name for name, value in _SECRETS.items() if value in body),
        "secrets_in_url": sorted(name for name, value in _SECRETS.items() if value in str(request.url)),
    }
    for name, value in request.headers.items():
        if name in _CREDENTIAL_HEADERS or name.startswith(_SHOWN_PREFIXES):
            facts[f"h.{name}"] = _labelled(value)
    if "anthropic-beta" in request.headers:  # a set of flags: the order they are listed in carries nothing
        facts["h.anthropic-beta"] = sorted(flag.strip() for flag in request.headers["anthropic-beta"].split(","))
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("AWS4-HMAC-SHA256 "):
        signature = parse_authorization(authorization)
        facts.update(
            {
                "h.authorization": "AWS4-HMAC-SHA256",
                "h.x-amz-date": "<timestamp>",
                "sigv4.access_key": _labelled(signature.access_key),
                "sigv4.region": signature.region,
                "sigv4.service": signature.service,
                "sigv4.signed_headers": list(signature.signed_headers),
                "sigv4.valid": signature_is_valid(request, _SECRETS["secret_key"]),
            }
        )
    return facts


def _isolate(env: pytest.MonkeyPatch, home: Path) -> None:
    """Only the case's variables remain: no ambient credential, endpoint, proxy or shared AWS file reaches the call."""
    for name in list(os.environ):
        if name.startswith(_ENV_PREFIXES) or name in _PROXY_VARIABLES:
            env.delenv(name)
    env.setenv("AWS_SHARED_CREDENTIALS_FILE", str(home / "credentials"))
    env.setenv("AWS_CONFIG_FILE", str(home / "config"))
    env.setenv("AWS_EC2_METADATA_DISABLED", "true")


async def _call(scenario: Scenario) -> bool:
    """Whether the call raised; the request it sent is already recorded."""
    try:
        llm = create_chat_model(
            scenario.model,
            streaming=scenario.stream,
            temperature=0.2,
            max_tokens=64,
            **scenario.kwargs,  # type: ignore[arg-type]  # free-form factory options of one scenario
        )
        runnable = llm.bind(response_format=JSON_SCHEMA) if scenario.structured else llm
        if scenario.stream:
            async for _ in runnable.astream("hi"):
                pass
        else:
            await runnable.ainvoke("hi")
    except Exception:  # whether a call raises at all is one of the recorded facts
        return True
    return False


def capture_credentials(monkeypatch: pytest.MonkeyPatch) -> dict[str, Verdict]:
    """Run the matrix on the installed stack; every case gets its own isolated environment and AWS home."""
    sent: list[httpx.Request] = []

    async def async_send(self: httpx.AsyncClient, request: httpx.Request, **kwargs: object) -> httpx.Response:
        request.read()
        sent.append(request)
        return canned_answer(request)

    def sync_send(self: httpx.Client, request: httpx.Request, **kwargs: object) -> httpx.Response:
        request.read()
        sent.append(request)
        return canned_answer(request)

    monkeypatch.setattr(httpx.AsyncClient, "send", async_send)
    monkeypatch.setattr(httpx.Client, "send", sync_send)

    async def main(root: Path) -> dict[str, Verdict]:
        verdicts: dict[str, Verdict] = {}
        for index, (name, scenario) in enumerate(SCENARIOS.items()):
            home = root / str(index)
            home.mkdir()
            for file_name, content in scenario.files.items():
                (home / file_name).write_text(content, encoding="utf-8")
            sent.clear()
            with pytest.MonkeyPatch.context() as env:
                _isolate(env, home)
                for variable, value in scenario.env.items():
                    env.setenv(variable, value)
                raised = await _call(scenario)
            calls = [request for request in sent if request.method == "POST"]
            verdicts[name] = {
                "raised": raised,
                "requests": len(calls),
                # any other traffic a model call causes (a configuration fetched from a third party, a token service)
                "other_requests": sorted(f"{r.method} {r.url.host}" for r in sent if r.method != "POST"),
                **(_facts(calls[0]) if calls else {}),
            }
        return verdicts

    with tempfile.TemporaryDirectory() as root:
        return asyncio.run(main(Path(root)))


def _record_to(path: Path, meta: dict[str, str]) -> None:
    with pytest.MonkeyPatch.context() as patch:
        cases = capture_credentials(patch)
    document: dict[str, object] = {"_meta": meta, "cases": cases}
    path.write_text(json.dumps(document, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    # OUT.json [key=value ...]: the key=value pairs describe the stack being recorded and land in ``_meta``
    _record_to(Path(sys.argv[1]), dict(arg.split("=", 1) for arg in sys.argv[2:]))
