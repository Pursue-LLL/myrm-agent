"""Chrome E2E: wiki browser clip → raw/ via live API."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    prepare_e2e_ui_session,
)


def _multipart_clip_post(api_url: str, fields: dict[str, str]) -> dict[str, object]:
    boundary = uuid.uuid4().hex
    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        )
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    request = urllib.request.Request(  # noqa: S310 - loopback E2E only
        f"{api_url.rstrip('/')}/api/v1/wiki/clip",
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        raise AssertionError(f"clip POST failed status={status} body={raw!r}") from exc

    if status != 202:
        raise AssertionError(f"clip POST expected 202 got {status}: {raw!r}")
    payload = json.loads(raw.decode("utf-8"))
    assert isinstance(payload, dict)
    return payload


def _poll_clip_job(api_url: str, job_id: str, *, timeout_sec: float = 30.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        payload = http_json(
            "GET",
            f"{api_url.rstrip('/')}/api/v1/wiki/clip/{job_id}",
            expected_statuses=frozenset({200}),
        )
        assert isinstance(payload, dict)
        last = payload
        state = str(payload.get("state", ""))
        if state in {"succeeded", "failed"}:
            return payload
        time.sleep(0.5)
    raise AssertionError(f"clip job timed out: {last}")


def _run_clip_api_assertions(api_url: str) -> None:
    stats_before = http_json("GET", f"{api_url.rstrip('/')}/api/v1/wiki/stats")
    assert isinstance(stats_before, dict)
    raw_before = int(stats_before.get("total_raw_files", 0))

    accepted = _multipart_clip_post(
        api_url,
        {
            "source_url": "https://example.com/e2e-clip-article",
            "title": "E2E Clip Article",
            "clip_mode": "full_page",
            "markdown": "# E2E Clip\n\nChrome E2E clip body.",
            "queue_compile": "false",
        },
    )
    job_id = str(accepted.get("job_id", ""))
    assert job_id

    final = _poll_clip_job(api_url, job_id)
    assert final.get("state") == "succeeded", final
    assert final.get("written") is True, final
    rel_path = str(final.get("relative_path", ""))
    assert rel_path

    stats_after = http_json("GET", f"{api_url.rstrip('/')}/api/v1/wiki/stats")
    assert isinstance(stats_after, dict)
    assert int(stats_after.get("total_raw_files", 0)) >= raw_before + 1


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wiki_clip_live_api_writes_raw() -> None:
    """POST /wiki/clip on live stack, poll job, assert raw count increases."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _ = ui_url  # session warmup touches UI; clip is API-first
    _run_clip_api_assertions(api_url)
