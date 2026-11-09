"""A Bedrock call signed with AWS credentials looks the credential chain up off the event loop.

The chain reads the shared credentials and config files (and, on a server, may call instance metadata or a token
service). Run inline in an ``async`` call that would stall every other request of the process, which the blockbuster
gate of this directory reports.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

pytest.importorskip("botocore")

from myrm_agent_harness.toolkits.llms.transport import http
from myrm_agent_harness.toolkits.llms.transport.client import LLMTransport

_SOURCES = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_BEARER_TOKEN_BEDROCK",
)
_ANSWER = {
    "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
    "stopReason": "end_turn",
    "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
}


async def test_the_credential_chain_is_resolved_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "credentials").write_text(
        "[default]\naws_access_key_id = AKIDEXAMPLE\naws_secret_access_key = secret\n", encoding="utf-8"
    )
    for name in _SOURCES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    sent: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=_ANSWER)

    monkeypatch.setattr(http, "_async_client", lambda proxy: httpx.AsyncClient(transport=httpx.MockTransport(respond)))

    await LLMTransport().acompletion(
        model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", messages=[{"role": "user", "content": "hi"}]
    )

    assert sent[0].headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/")
