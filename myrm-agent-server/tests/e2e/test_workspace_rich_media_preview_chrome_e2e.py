"""Chrome E2E: workspace browser rich-media file preview.

Verifies the real end-to-end path for rich media in the workspace file browser:
backend /files/browse/content binary streaming (no 1MB truncation, correct MIME)
plus the frontend RichMediaFilePreview dispatcher rendering images / PDF / text,
and the unsupported-type fallback with a download button.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_MAX_ATTEMPTS = 3
_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "open_mcp_page",
    "MUX",
    "CDP",
    "Chrome MCP",
    "Browser Orchestrator",
    "No target with given id",
    "connection reset",
    "wait_for_state",
    "Browser state did not become ready",
    "Page shell did not hydrate",
    "E2E_MUX_DAEMONS",
    "transport dead",
    "transport unavailable",
    "recover_mux_transport",
    "recover_mux",
    "chrome-error",
    "Runtime.evaluate",
    "CDP request timeout",
    "no-bridge",
    "PARENT_LEASE_NOT_ACTIVE",
    "E2E_LEASE_INVALID",
    "Connection refused",
    "E2E_SHARED_API_UNAVAILABLE",
    "E2E_RUNTIME_BINDING_FAILED",
    "Browser Orchestrator error",
    "MUX_ATTACH_RESTART_BLOCKED_PARALLEL",
    "attach-timeout",
)

_PREVIEW_FILES = ("preview.png", "preview.pdf", "bundle.zip", "readme.txt")


def _wait_timeout_sec() -> float:
    try:
        from e2e_core.shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            return 180.0
    except ImportError:
        pass
    return 90.0


_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""


def _attach_chat_probe_js(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {{
    return {{ ok: false, err: 'no-bridge' }};
  }}
  await bridge.attachToChat({chat_id_json});
  const domDeadline = Date.now() + 30_000;
  while (Date.now() < domDeadline) {{
    if (
      document.querySelector('[data-message-end]')
      || document.querySelector('[data-chat-input]')
    ) {{
      break;
    }}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }}
  const snap = bridge.turnSnapshot?.() ?? {{}};
  return {{
    ok: snap.chatId === {chat_id_json} && (snap.userCount ?? 0) >= 1,
    snap,
  }};
}})()"""


def _open_workspace_tab_js() -> str:
    return """(() => {
  const tab = Array.from(document.querySelectorAll('button')).find((b) =>
    /Files|文件|檔案/.test(b.textContent || ''),
  );
  if (tab) tab.click();
  const store = window.__myrmChatStore?.getState?.() ?? null;
  const ready = Boolean(tab);
  return {
    ok: ready,
    ready,
    text: tab?.textContent || '',
    store: store
      ? {
          chatId: store.chatId,
          actionMode: store.actionMode,
          workspaceDir: store.workspaceDir,
          messages: store.messages?.length ?? 0,
        }
      : null,
    bodyLen: (document.body?.innerText || '').length,
    bodySample: (document.body?.innerText || '').slice(0, 240),
  };
})()"""


def _click_file_js(filename: str) -> str:
    return f"""(() => {{
  const name = {json.dumps(filename)};
  const btn = Array.from(document.querySelectorAll('button')).find((b) =>
    (b.textContent || '').includes(name),
  );
  if (btn) btn.click();
  const ready = Boolean(btn);
  return {{ ok: ready, ready }};
}})()"""


def _preview_ready_js() -> str:
    return """(() => ({
  ready: Boolean(document.querySelector('[data-testid="workspace-file-preview"]')),
}))()"""


def _preview_closed_js() -> str:
    return """(() => ({
  ready: !document.querySelector('[data-testid="workspace-file-preview"]'),
}))()"""


def _close_preview_js() -> str:
    return """(() => {
  const panel = document.querySelector('[data-testid="workspace-file-preview"]');
  if (!panel) return { ok: false };
  const btn = Array.from(panel.querySelectorAll('button')).find((b) =>
    /Close|关闭|關閉/i.test(b.title || ''),
  );
  if (!btn) return { ok: false };
  btn.click();
  return { ok: true };
})()"""


def _image_preview_ready_js() -> str:
    return """(() => {
  const panel = document.querySelector('[data-testid="workspace-file-preview"]');
  const img = panel?.querySelector('img');
  return {
    ready: Boolean(img && img.naturalWidth > 0),
    width: img?.naturalWidth || 0,
    src: img?.src || '',
  };
})()"""


def _pdf_preview_ready_js() -> str:
    return """(() => {
  const panel = document.querySelector('[data-testid="workspace-file-preview"]');
  return {
    ready: Boolean(panel?.querySelector('.react-pdf__Document, canvas')),
  };
})()"""


def _unsupported_preview_ready_js() -> str:
    return """(() => ({
  ready: Boolean(document.querySelector('[data-testid="workspace-preview-unsupported"]')),
}))()"""


def _text_preview_ready_js() -> str:
    return """(() => {
  const panel = document.querySelector('[data-testid="workspace-file-preview"]');
  const code = panel?.querySelector('code');
  return { ready: Boolean(code), text: code?.textContent || '' };
})()"""


def _seed_rich_media_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-rich-media-preview-fixture",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    ui_path = str(seeded.get("ui_path") or "")
    assert chat_id.startswith("e2ermd")
    assert ui_path == f"/{chat_id}"
    return seeded


def _open_and_switch_to_workspace_tab(
    client: object, page: object, chat_id: str, page_url: str
) -> None:
    bridge_ready = wait_for_react_e2e_bridge(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        timeout_sec=_wait_timeout_sec(),
        page_url=page_url,
    )
    assert bridge_ready.get("ready") is True, json.dumps(
        bridge_ready,
        ensure_ascii=False,
    )

    attached = client.evaluate(  # type: ignore[attr-defined]
        page,
        _attach_chat_probe_js(chat_id),
        timeout_sec=_wait_timeout_sec(),
    )
    assert isinstance(attached, dict) and attached.get("ok") is True, attached

    dismiss_blocking_modals(client, page)  # type: ignore[arg-type]

    tab_state = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        _open_workspace_tab_js(),
        timeout_sec=_wait_timeout_sec(),
    )
    assert tab_state.get("ok") is True, json.dumps(
        tab_state,
        ensure_ascii=False,
    )


def _assert_preview_flows(client: object, page: object) -> None:
    for filename in _PREVIEW_FILES:
        clicked = wait_for_state(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            _click_file_js(filename),
            timeout_sec=30.0,
        )
        assert clicked.get("ok") is True, json.dumps(
            clicked,
            ensure_ascii=False,
        )

        preview = wait_for_state(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            _preview_ready_js(),
            timeout_sec=30.0,
        )
        assert preview.get("ready") is True, json.dumps(
            preview,
            ensure_ascii=False,
        )

        if filename == "preview.png":
            image = wait_for_state(
                client,  # type: ignore[arg-type]
                page,  # type: ignore[arg-type]
                _image_preview_ready_js(),
                timeout_sec=30.0,
            )
            assert image.get("ready") is True, json.dumps(
                image,
                ensure_ascii=False,
            )
            assert "/api/v1/files/browse/content" in str(image.get("src") or ""), image
        elif filename == "preview.pdf":
            pdf = wait_for_state(
                client,  # type: ignore[arg-type]
                page,  # type: ignore[arg-type]
                _pdf_preview_ready_js(),
                timeout_sec=45.0,
            )
            assert pdf.get("ready") is True, json.dumps(
                pdf,
                ensure_ascii=False,
            )
        elif filename == "bundle.zip":
            unsupported = wait_for_state(
                client,  # type: ignore[arg-type]
                page,  # type: ignore[arg-type]
                _unsupported_preview_ready_js(),
                timeout_sec=30.0,
            )
            assert unsupported.get("ready") is True, json.dumps(
                unsupported,
                ensure_ascii=False,
            )
        else:
            text = wait_for_state(
                client,  # type: ignore[arg-type]
                page,  # type: ignore[arg-type]
                _text_preview_ready_js(),
                timeout_sec=30.0,
            )
            assert text.get("ready") is True, json.dumps(
                text,
                ensure_ascii=False,
            )
            assert "rich media preview E2E fixture" in str(text.get("text") or ""), text

        closed_ok = client.evaluate(page, _close_preview_js(), timeout_sec=15.0)  # type: ignore[attr-defined]
        assert isinstance(closed_ok, dict) and closed_ok.get("ok") is True, closed_ok
        closed = wait_for_state(
            client,  # type: ignore[arg-type]
            page,  # type: ignore[arg-type]
            _preview_closed_js(),
            timeout_sec=15.0,
        )
        assert closed.get("ready") is True, json.dumps(
            closed,
            ensure_ascii=False,
        )


def _run_preview_assertions(api_url: str, ui_url: str) -> None:
    seeded = _seed_rich_media_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    target_url = f"{ui_url.rstrip('/')}/{chat_id}"

    warm_ui_route("/")
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(target_url, timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
        _open_and_switch_to_workspace_tab(client, page, chat_id, target_url)
        _assert_preview_flows(client, page)


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    if "E2E_USER_CLOSED_TAB" in text or "E2E_ORCHESTRATOR_LEASE_DENIED" in text:
        return False
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


def _force_mux_heal_before_retry() -> None:
    _require_e2e_cdp_ready(budget_sec=45.0)
    try:
        from mux.attach_force_restart import force_mux_attach_restart_scoped

        force_mux_attach_restart_scoped(reason="workspace rich-media preview retry")
    except RuntimeError as exc:
        if "MUX_ATTACH_RESTART_BLOCKED_PARALLEL" not in str(exc):
            raise
    time.sleep(5.0)


def _run_with_transport_retry(
    runner: Callable[..., None], api_url: str, ui_url: str
) -> None:
    last_error: BaseException | None = None
    for _attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            runner(api_url, ui_url)
            return
        except Exception as exc:
            last_error = exc
            if _attempt >= _MAX_ATTEMPTS or not _is_transport_retryable(exc):
                raise
            _force_mux_heal_before_retry()
    if last_error is not None:
        raise last_error


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD", private_reason="exclusive_backend"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_workspace_rich_media_preview_renders_files() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_preview_assertions, api_url, ui_url)
