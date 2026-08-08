"""Chrome E2E: OpenAPI fail-loud errors surface in real WebUI chat (SSE + metadata)."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import wait_e2e_provider_ready  # noqa: E402
from chrome_mcp_client import ChromeMcpClient  # noqa: E402
from dev_gate_contract import EvaluateIntent  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_allowlist_live_e2e import _AGENT_READY_JS
from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    prepare_e2e_ui_session,
    warm_ui_route,
)
from tests.support.chrome_openapi_fail_loud_e2e import (
    PREPARE_AGENT_CHAT_JS,
    WAIT_CHAT_IDLE_JS,
    send_and_wait_openapi_error_js,
    wait_agent_applied_js,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease


def _heavy_openapi_spec_yaml() -> str:
    """Inline OpenAPI spec that exceeds AGGREGATE_DIRECT_TOKEN_BUDGET (1200 tok)."""
    lines = [
        "openapi: 3.0.0",
        "info:",
        "  title: E2E OpenAPI Budget Test",
        "  version: 1.0.0",
        "servers:",
        "  - url: https://example.com",
        "paths:",
    ]
    for index in range(12):
        summary = "x" * 800
        lines.extend(
            [
                f"  /items/{index}:",
                "    post:",
                f"      operationId: heavyOp{index}",
                f"      summary: {summary}",
                "      requestBody:",
                "        required: true",
                "        content:",
                "          application/json:",
                "            schema:",
                "              type: object",
                "              properties:",
            ]
        )
        for field_index in range(8):
            lines.extend(
                [
                    f"                field_{field_index}:",
                    "                  type: string",
                    f"                  description: {'y' * 200}",
                ]
            )
        lines.extend(
            [
                "      responses:",
                '        "200":',
                "          description: ok",
            ]
        )
    return "\n".join(lines)


def _create_agent(api_url: str, *, openapi_services: list[dict[str, object]], label: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"OpenAPI Fail Loud E2E {label} {suffix}",
        "description": f"Chrome E2E for OpenAPI fail-loud ({label})",
        "system_prompt": "You are a test agent.",
        "mcp_ids": [],
        "skill_ids": [],
        "enabled_builtin_tools": [],
        "openapi_services": openapi_services,
    }
    created = http_json("POST", f"{api_url}/api/v1/user-agents", payload)
    assert isinstance(created, dict)
    data = created.get("data") if isinstance(created.get("data"), dict) else created
    agent_id = str(data.get("id") or "")
    assert agent_id
    return agent_id


def _assert_agent_openapi_services(
    api_url: str,
    agent_id: str,
    *,
    min_count: int = 1,
) -> None:
    fetched = http_json("GET", f"{api_url}/api/v1/user-agents/{agent_id}")
    assert isinstance(fetched, dict)
    data = fetched.get("data") if isinstance(fetched.get("data"), dict) else fetched
    services = data.get("openapi_services")
    assert isinstance(services, list) and len(services) >= min_count, (
        f"agent {agent_id} missing openapi_services: {data!r}"
    )


def _delete_agent(api_url: str, agent_id: str) -> None:
    try:
        http_json(
            "DELETE",
            f"{api_url}/api/v1/user-agents/{agent_id}",
            expected_statuses=frozenset({200, 204}),
        )
    except RuntimeError:
        pass


async def _wait_agent_applied(
    chat: McpChatSession,
    *,
    expected_agent_id: str,
    timeout_sec: float = 90.0,
) -> None:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    js = wait_agent_applied_js(expected_agent_id)
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        raw = await chat.evaluate(js, intent=EvaluateIntent.AGENT_SUBMIT)
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ok") is True:
            return
        await asyncio.sleep(1.0)
    raise AssertionError(f"E2E agent not applied: expected={expected_agent_id!r} last={last!r}")


async def _wait_bridge_ready(chat: McpChatSession, *, timeout_sec: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        raw = await chat.evaluate(_AGENT_READY_JS, intent=EvaluateIntent.BRIDGE_POLL)
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ready") is True:
            return
        await asyncio.sleep(1.0)
    raise AssertionError(f"E2E chat bridge not ready: {last!r}")


async def _open_agent_page(client: ChromeMcpClient, agent_url: str, api_url: str) -> object:
    last_exc: RuntimeError | None = None
    for attempt in range(4):
        if attempt > 0:
            wait_e2e_provider_ready(api_url=api_url, timeout_sec=30.0)
            await asyncio.sleep(2.0 * attempt)
        try:
            return await asyncio.to_thread(client.new_page, agent_url, timeout_ms=120_000)
        except RuntimeError as exc:
            if "E2E_RUNTIME_BINDING_FAILED" not in str(exc):
                raise
            last_exc = exc
    assert last_exc is not None
    raise last_exc


async def _run_openapi_fail_loud_ui(
    *,
    agent_id: str,
    agent_path: str,
    agent_url: str,
    expected_error_type: str,
    message_pattern: str,
) -> dict[str, object]:
    api_url = get_e2e_api_url()
    heartbeat_e2e_lease()
    prepare_e2e_ui_session(api_url)
    await asyncio.to_thread(warm_ui_route, agent_path)

    client = ChromeMcpClient(request_timeout_sec=120.0)
    await asyncio.to_thread(client.start)
    page = None
    try:
        page = await _open_agent_page(client, agent_url, api_url)
        chat = McpChatSession(client, page)
        await chat.bootstrap(agent_url, timeout_sec=120.0)
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
        await _wait_bridge_ready(chat)
        await _wait_agent_applied(chat, expected_agent_id=agent_id)
        prep = await chat.evaluate(
            PREPARE_AGENT_CHAT_JS,
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        assert isinstance(prep, dict) and prep.get("ok") is True, prep
        assert prep.get("agentId") == agent_id, prep
        assert prep.get("actionMode") == "agent", prep
        idle = await chat.evaluate(
            WAIT_CHAT_IDLE_JS,
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        assert isinstance(idle, dict) and idle.get("ok") is True, idle
        js = send_and_wait_openapi_error_js(
            expected_error_type=expected_error_type,
            message_pattern=message_pattern,
        )
        outcome = await chat.evaluate(js, intent=EvaluateIntent.AGENT_SUBMIT)
        return outcome if isinstance(outcome, dict) else {"ok": False, "raw": outcome}
    finally:
        if page is not None:
            try:
                await asyncio.to_thread(client.close_page, page, ignore_errors=True)
            except RuntimeError:
                pass
        await asyncio.to_thread(client.close)


def _assert_openapi_outcome(
    outcome: dict[str, object],
    *,
    expected_error_type: str,
) -> None:
    assert outcome.get("ok") is True, json.dumps(outcome, ensure_ascii=False)
    assert outcome.get("sseHasError") is True, json.dumps(outcome, ensure_ascii=False)
    matched = outcome.get("matched")
    assert matched in {"metadata", "progressStep"}, (
        f"expected chat metadata or progressStep, got {matched!r}: "
        f"{json.dumps(outcome, ensure_ascii=False)}"
    )
    error_type = outcome.get("errorType")
    if isinstance(error_type, str) and error_type:
        assert error_type == expected_error_type, outcome


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_openapi_load_fail_shows_chat_error_in_real_ui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Broken OpenAPI spec URL must fail loud with openapi_load_failed in chat."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url().rstrip("/")
    if not wait_e2e_provider_ready(api_url=api_url):
        pytest.fail("Provider config not ready for OpenAPI load-fail Chrome E2E")

    agent_id = _create_agent(
        api_url,
        label="load_failed",
        openapi_services=[
            {
                "name": "bad_svc",
                "enabled": True,
                "spec_content": ":::not-valid-openapi-yaml:::",
            }
        ],
    )
    _assert_agent_openapi_services(api_url, agent_id)
    agent_path = f"/?agentId={agent_id}"
    agent_url = f"{ui_url}{agent_path}"
    e2e_resource_ledger.register("agent", agent_id)

    try:
        outcome = await _run_openapi_fail_loud_ui(
            agent_id=agent_id,
            agent_path=agent_path,
            agent_url=agent_url,
            expected_error_type="openapi_load_failed",
            message_pattern=(
                r"OpenAPI services are enabled but no tools|已启用 OpenAPI 服务但未加载任何工具"
            ),
        )
        _assert_openapi_outcome(outcome, expected_error_type="openapi_load_failed")
    finally:
        _delete_agent(api_url, agent_id)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_openapi_budget_exceeded_shows_chat_error_in_real_ui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Heavy inline OpenAPI schema must fail loud with openapi_direct_budget_exceeded."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url().rstrip("/")
    if not wait_e2e_provider_ready(api_url=api_url):
        pytest.fail("Provider config not ready for OpenAPI budget Chrome E2E")

    agent_id = _create_agent(
        api_url,
        label="budget_exceeded",
        openapi_services=[
            {
                "name": "heavy_svc",
                "enabled": True,
                "spec_content": _heavy_openapi_spec_yaml(),
            }
        ],
    )
    _assert_agent_openapi_services(api_url, agent_id)
    agent_path = f"/?agentId={agent_id}"
    agent_url = f"{ui_url}{agent_path}"
    e2e_resource_ledger.register("agent", agent_id)

    try:
        outcome = await _run_openapi_fail_loud_ui(
            agent_id=agent_id,
            agent_path=agent_path,
            agent_url=agent_url,
            expected_error_type="openapi_direct_budget_exceeded",
            message_pattern=(
                r"exceeds the Turn1 direct bind budget|超出 Turn1 直接绑定预算|"
                r"exceeds Turn1 direct budget|超出.*直接绑定预算"
            ),
        )
        _assert_openapi_outcome(outcome, expected_error_type="openapi_direct_budget_exceeded")
    finally:
        _delete_agent(api_url, agent_id)
