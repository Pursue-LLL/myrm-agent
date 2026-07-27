"""Chrome E2E: empty file_write rejection — READ lane FileMutationWarning banner."""

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

_FIXTURE_ANSWER = "Empty write E2E fixture answer."

_MUTATION_BANNER_READY_JS = f"""(() => {{
  const target = {json.dumps(_FIXTURE_ANSWER)};
  const store = window.__myrmChatStore?.getState?.();
  const msg = (store?.messages || []).find(
    (item) => item.role === 'assistant' && (item.content || '').includes(target),
  );
  const failures = Array.isArray(msg?.fileMutationFailures) ? msg.fileMutationFailures : [];
  const bodyText = document.body?.innerText || '';
  const hasTitle = /File Modification Failed|文件修改失败/i.test(bodyText);
  const hasCount = /file modification failed|文件修改失败|个文件修改失败/i.test(bodyText);
  const hasError = /Cannot write empty file content/i.test(bodyText)
    || failures.some((item) => String(item?.error_preview || '').includes('Cannot write empty'));
  return {{
    ready: failures.length > 0 && hasTitle && hasCount,
    failureCount: failures.length,
    hasTitle,
    hasCount,
    hasError,
    sample: bodyText.slice(0, 500),
  }};
}})()"""


def _seed_file_mutation_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-file-mutation-fixture?variant=empty_write",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    message_id = str(seeded.get("message_id") or "")
    ui_path = str(seeded.get("ui_path") or "")
    assert chat_id.startswith("e2efmut")
    assert len(message_id) >= 8
    assert ui_path == f"/{chat_id}"
    return seeded


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_file_write_empty_shows_mutation_warning_banner() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_file_mutation_fixture(api_url)
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

        banner = wait_for_state(
            client,
            page,
            _MUTATION_BANNER_READY_JS,
            timeout_sec=30.0,
        )
        assert banner.get("ready") is True, json.dumps(banner, ensure_ascii=False)
        assert int(banner.get("failureCount") or 0) >= 1

        expanded = wait_for_state(
            client,
            page,
            """(() => {
              const btn = Array.from(document.querySelectorAll('button')).find((el) => {
                const text = el.textContent || '';
                return /File Modification Failed|文件修改失败/i.test(text);
              });
              if (!btn) return { ready: false, err: 'banner-button-missing' };
              btn.click();
              const store = window.__myrmChatStore?.getState?.();
              const failures = (store?.messages || [])
                .flatMap((msg) => Array.isArray(msg.fileMutationFailures) ? msg.fileMutationFailures : []);
              const hasStoreError = failures.some((item) =>
                String(item?.error_preview || '').includes('Cannot write empty file content'),
              );
              const bodyText = document.body?.innerText || '';
              const hasDomError = /Cannot write empty file content/i.test(bodyText);
              const hasPath = /empty_write_e2e\\.txt/i.test(bodyText);
              return {
                ready: hasStoreError && (hasDomError || hasPath),
                hasStoreError,
                hasDomError,
                hasPath,
                sample: bodyText.slice(0, 500),
              };
            })()""",
            timeout_sec=15.0,
        )
        assert expanded.get("ready") is True, json.dumps(expanded, ensure_ascii=False)


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_file_write_empty_mutation_banner_survives_page_reload() -> None:
    """Hydrate from DB: reload must still show FileMutationWarning from metadata."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_file_mutation_fixture(api_url)
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

        banner_before_reload = wait_for_state(
            client,
            page,
            _MUTATION_BANNER_READY_JS,
            timeout_sec=30.0,
        )
        assert banner_before_reload.get("ready") is True, json.dumps(
            banner_before_reload,
            ensure_ascii=False,
        )

        reload_mcp_page(client, page)
        dismiss_blocking_modals(client, page)

        reloaded = wait_for_state(
            client,
            page,
            _MUTATION_BANNER_READY_JS,
            timeout_sec=120.0,
        )
        assert reloaded.get("ready") is True, json.dumps(reloaded, ensure_ascii=False)
