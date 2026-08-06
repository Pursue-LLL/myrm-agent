"""Chrome E2E: wiki browser clip → raw/ via live API."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    warm_ui_route,
)


def _multipart_clip_post(
    api_url: str,
    fields: dict[str, str],
    *,
    agent_id: str | None = None,
) -> dict[str, object]:
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

    clip_url = f"{api_url.rstrip('/')}/api/v1/wiki/clip"
    if agent_id:
        clip_url = f"{clip_url}?agent_id={urllib.parse.quote(agent_id, safe='')}"

    request = urllib.request.Request(  # noqa: S310 - loopback E2E only
        clip_url,
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
            "html": "<article><h1>E2E Clip</h1><p>Chrome E2E HTML clip body.</p></article>",
            "markdown": "",
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


def _create_clip_e2e_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Wiki Clip E2E {suffix}",
        "description": "Chrome E2E scoped wiki clip agent",
        "system_prompt": "E2E wiki clip scoped vault test agent.",
        "skill_ids": [],
        "mcp_ids": [],
    }
    created = http_json("POST", f"{api_url.rstrip('/')}/api/v1/user-agents", payload)
    assert isinstance(created, dict)
    agent_id = (
        created.get("data", {}).get("id")
        if isinstance(created.get("data"), dict)
        else created.get("id")
    )
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _wiki_stats(api_url: str, agent_id: str | None = None) -> dict[str, object]:
    url = f"{api_url.rstrip('/')}/api/v1/wiki/stats"
    if agent_id:
        url = f"{url}?agent_id={urllib.parse.quote(agent_id, safe='')}"
    payload = http_json("GET", url)
    assert isinstance(payload, dict)
    return payload


def _run_clip_agent_scoped_assertions(api_url: str) -> None:
    agent_id = _create_clip_e2e_agent(api_url)
    stats_before = _wiki_stats(api_url, agent_id)
    raw_before = int(stats_before.get("total_raw_files", 0))

    accepted = _multipart_clip_post(
        api_url,
        {
            "source_url": f"https://example.com/e2e-clip-agent-{uuid.uuid4().hex[:8]}",
            "title": "E2E Agent Scoped Clip",
            "clip_mode": "full_page",
            "html": "<article><h1>E2E Agent Scoped</h1><p>Scoped vault HTML body.</p></article>",
            "markdown": "",
            "queue_compile": "false",
        },
        agent_id=agent_id,
    )
    job_id = str(accepted.get("job_id", ""))
    assert job_id

    final = _poll_clip_job(api_url, job_id)
    assert final.get("state") == "succeeded", final
    assert final.get("written") is True, final

    stats_after = _wiki_stats(api_url, agent_id)
    assert int(stats_after.get("total_raw_files", 0)) >= raw_before + 1


def _run_clip_conflict_assertions(api_url: str) -> None:
    source_url = f"https://example.com/e2e-conflict-{uuid.uuid4().hex[:8]}"
    base_fields = {
        "source_url": source_url,
        "title": "E2E Conflict Clip",
        "clip_mode": "full_page",
        "queue_compile": "false",
    }
    accepted = _multipart_clip_post(api_url, {**base_fields, "markdown": "# First clip"})
    first = _poll_clip_job(api_url, str(accepted.get("job_id", "")))
    assert first.get("written") is True, first

    accepted_repeat = _multipart_clip_post(
        api_url,
        {**base_fields, "markdown": "# Duplicate attempt"},
    )
    repeat = _poll_clip_job(api_url, str(accepted_repeat.get("job_id", "")))
    assert repeat.get("conflict") is True, repeat
    assert repeat.get("written") is False, repeat


def _run_extension_origin_seed_assertion(api_url: str, ui_url: str) -> None:
    cfg = http_json("GET", f"{api_url.rstrip('/')}/api/v1/extension/clip-agent")
    assert isinstance(cfg, dict)
    origin = str(cfg.get("web_ui_origin", "") or "")
    assert origin.startswith("http"), f"expected web_ui_origin from UI warmup, got {cfg!r}"
    assert ui_url.rstrip("/").startswith(origin.rstrip("/")) or origin.rstrip("/").startswith(
        ui_url.rstrip("/")
    )


def _ensure_extension_web_ui_origin_seeded(api_url: str, ui_url: str) -> None:
    """AppLayout mount seeds clip-agent web_ui_origin; HTTP warm alone is insufficient."""
    home_url = f"{ui_url.rstrip('/')}/"
    warm_ui_route("/")
    deadline = time.monotonic() + 90.0
    with open_mcp_page(home_url, timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=home_url)
        wait_for_react_e2e_bridge(
            client,
            page,
            timeout_sec=_warm_ui_parallel_wait_sec(60.0),
            page_url=home_url,
        )
        seeded = False
        while time.monotonic() < deadline:
            cfg = http_json("GET", f"{api_url.rstrip('/')}/api/v1/extension/clip-agent")
            assert isinstance(cfg, dict)
            origin = str(cfg.get("web_ui_origin", "") or "")
            if origin.startswith("http"):
                seeded = True
                break
            time.sleep(0.5)
        if not seeded:
            raise AssertionError("web_ui_origin not seeded after AppLayout mount")
    _run_extension_origin_seed_assertion(api_url, ui_url)


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
    _ensure_extension_web_ui_origin_seeded(api_url, ui_url)
    _run_clip_api_assertions(api_url)
    _run_clip_agent_scoped_assertions(api_url)
    _run_clip_conflict_assertions(api_url)
