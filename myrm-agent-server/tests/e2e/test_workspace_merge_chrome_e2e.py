"""Chrome E2E: workspace merge failure — READ lane WorkspaceMergeWarning + reload hydrate."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_FIXTURE_ANSWER = "Workspace merge E2E fixture answer."
_FIXTURE_ERROR = "task_index=1: No space left on device"


def _merge_panel_ready_js() -> str:
    return f"""(() => {{
  const target = {json.dumps(_FIXTURE_ANSWER)};
  const store = window.__myrmChatStore?.getState?.();
  const msg = (store?.messages || []).find(
    (item) => item.role === 'assistant' && (item.content || '').includes(target),
  );
  const failures = Array.isArray(msg?.workspaceMergeFailures)
    ? msg.workspaceMergeFailures
    : [];
  const panel = document.querySelector('[data-testid="workspace-merge-warning"]');
  const bodyText = document.body?.innerText || '';
  const hasTitle = /Workspace Merge Failed|工作区合并失败|工作區合併失敗/i.test(bodyText);
  const hasError = /task_index=1/i.test(bodyText)
    || failures.some((item) => String(item?.message || '').includes('task_index=1'));
  return {{
    ready: failures.length > 0 && !!panel && hasTitle && hasError,
    failureCount: failures.length,
    hasPanel: !!panel,
    hasTitle,
    hasError,
    sample: bodyText.slice(0, 500),
  }};
}})()"""


def _seed_workspace_merge_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-workspace-merge-fixture?variant=batch_merge_fail",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    message_id = str(seeded.get("message_id") or "")
    ui_path = str(seeded.get("ui_path") or "")
    assert chat_id.startswith("e2ewsmr")
    assert len(message_id) >= 8
    assert ui_path == f"/{chat_id}"
    return seeded


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_workspace_merge_shows_warning_panel() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_workspace_merge_fixture(api_url)
    chat_id = str(seeded["chat_id"])

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        message_ready = wait_for_state(
            client,
            page,
            f"""(() => {{
              const target = {json.dumps(_FIXTURE_ANSWER)};
              const store = window.__myrmChatStore?.getState?.();
              const msg = (store?.messages || []).find(
                (item) => item.role === 'assistant' && (item.content || '').includes(target),
              );
              return {{ ready: !!msg, count: store?.messages?.length ?? 0 }};
            }})()""",
            timeout_sec=90.0,
        )
        assert message_ready.get("ready") is True, json.dumps(
            message_ready,
            ensure_ascii=False,
        )

        dismiss_blocking_modals(client, page)

        panel = wait_for_state(
            client,
            page,
            _merge_panel_ready_js(),
            timeout_sec=30.0,
        )
        assert panel.get("ready") is True, json.dumps(panel, ensure_ascii=False)
        assert int(panel.get("failureCount") or 0) >= 1


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_workspace_merge_warning_survives_page_reload() -> None:
    """Hydrate from DB: reload must still show WorkspaceMergeWarning from metadata."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_workspace_merge_fixture(api_url)
    chat_id = str(seeded["chat_id"])

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        message_ready = wait_for_state(
            client,
            page,
            f"""(() => {{
              const target = {json.dumps(_FIXTURE_ANSWER)};
              const store = window.__myrmChatStore?.getState?.();
              const msg = (store?.messages || []).find(
                (item) => item.role === 'assistant' && (item.content || '').includes(target),
              );
              return {{ ready: !!msg }};
            }})()""",
            timeout_sec=90.0,
        )
        assert message_ready.get("ready") is True, json.dumps(
            message_ready,
            ensure_ascii=False,
        )

        dismiss_blocking_modals(client, page)

        before_reload = wait_for_state(
            client,
            page,
            _merge_panel_ready_js(),
            timeout_sec=30.0,
        )
        assert before_reload.get("ready") is True, json.dumps(
            before_reload,
            ensure_ascii=False,
        )

        reload_mcp_page(client, page)
        dismiss_blocking_modals(client, page)

        after_reload = wait_for_state(
            client,
            page,
            _merge_panel_ready_js(),
            timeout_sec=120.0,
        )
        assert after_reload.get("ready") is True, json.dumps(
            after_reload,
            ensure_ascii=False,
        )
