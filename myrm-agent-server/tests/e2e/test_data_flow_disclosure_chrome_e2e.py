"""Chrome MCP E2E: Settings Security Data Flow disclosure panel (read-only egress UI)."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_settings_subroute,
    wait_e2e_provider_ready,
    wait_for_settings_layout,
    wait_for_state,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import infer_provider_id, seed_live_e2e_providers

DATA_FLOW_PANEL_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTitle =
    /Data Flow & Privacy Disclosure|数据流向与隐私披露/.test(text);
  const hasEgress =
    /External Egress|外部出站与第三方 API|第三方外部出站流向/.test(text);
  const hasRights =
    /Your Data Rights|您的数据权利/.test(text);
  const anchor = Array.from(document.querySelectorAll('h2,h3,h4')).find((el) =>
    /Data Flow|数据流向/.test(el.textContent || ''),
  );
  if (anchor && typeof anchor.scrollIntoView === 'function') {
    anchor.scrollIntoView({ block: 'center' });
  }
  return {
    ready: hasTitle && hasEgress && hasRights,
    hasTitle,
    hasEgress,
    hasRights,
    sample: text.slice(0, 1200),
  };
})()"""


COMPLIANCE_EXPORT_BUTTON_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const exportBtn = buttons.find((btn) =>
    /Download compliance export|下载合规导出|合规导出|下载合规导出包/.test(btn.textContent || ''),
  );
  return {
    ready: Boolean(exportBtn),
    label: exportBtn?.textContent?.trim() ?? null,
  };
})()"""

LOCAL_DOMAIN_JS = """(() => {
  const text = document.body?.innerText || '';
  return {
    ready: /Local Storage & Processing|本地存储与处理/.test(text),
  };
})()"""

CONTROL_PLANE_JS = """(() => {
  const text = document.body?.innerText || '';
  return {
    ready: /Control Plane Coordination|控制平面协调/.test(text),
  };
})()"""

CLICK_COMPLIANCE_EXPORT_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const exportBtn = buttons.find((btn) =>
    /Download compliance export|下载合规导出|合规导出|下载合规导出包/.test(btn.textContent || ''),
  );
  if (!exportBtn) {
    return { ok: false, err: 'export button missing' };
  }
  exportBtn.click();
  return { ok: true, label: exportBtn.textContent?.trim() ?? null };
})()"""

EXPORT_FEEDBACK_JS = """(() => {
  const text = document.body?.innerText || '';
  const exporting = /Preparing export|正在准备导出|导出准备中/.test(text);
  const success = /Compliance export downloaded|合规导出已下载|导出成功|合规导出包已下载/.test(text);
  const failed = /Export failed|导出失败/.test(text);
  const button = Array.from(document.querySelectorAll('button')).find((btn) =>
    /Download compliance export|下载合规导出|合规导出|下载合规导出包/.test(btn.textContent || ''),
  );
  return {
    ready: success || failed || Boolean(button && !button.disabled && !exporting),
    exporting,
    success,
    failed,
    buttonDisabled: Boolean(button?.disabled),
  };
})()"""


def provider_egress_visible_js(provider_id: str) -> str:
    return f"""(() => {{
  const anchor = Array.from(document.querySelectorAll('h2,h3,h4')).find((el) =>
    /Data Flow|数据流向/.test(el.textContent || ''),
  );
  if (anchor && typeof anchor.scrollIntoView === 'function') {{
    anchor.scrollIntoView({{ block: 'center' }});
  }}
  const text = document.body?.innerText || '';
  const hasProvider = /{provider_id}|MiniMax/i.test(text);
  const hasLlm = /LLM Inference Providers|LLM 推理提供商|大模型推理供应商/.test(text);
  const hasCloudBadge = /Cloud API|云端 API/.test(text);
  const activeCount = text.match(/(\\d+)\\s*active|(\\d+)\\s*个活跃/);
  return {{
    ready: hasProvider && hasLlm && Boolean(activeCount),
    hasProvider,
    hasLlm,
    hasCloudBadge,
    activeCount: activeCount ? activeCount[0] : null,
    sample: text.slice(0, 1600),
  }};
}})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(240)
def test_settings_security_shows_data_flow_disclosure_panel() -> None:
    security_url = f"{get_e2e_ui_url().rstrip('/')}/settings/security"
    warm_ui_route("/settings/security")
    with open_settings_subroute("/settings/security", timeout_ms=90_000) as (
        client,
        page,
    ):
        client.navigate(page, security_url, timeout_ms=90_000)
        dismiss_blocking_modals(client, page, recover_url=security_url)
        wait_for_settings_layout(client, page, page_url=security_url, timeout_sec=60.0)

        panel = wait_for_state(
            client,
            page,
            DATA_FLOW_PANEL_READY_JS,
            timeout_sec=90.0,
            page_url=security_url,
        )
        assert panel.get("ready") is True, panel
        assert panel.get("hasTitle") is True, panel
        assert panel.get("hasEgress") is True, panel
        assert panel.get("hasRights") is True, panel

        local_domain = wait_for_state(client, page, LOCAL_DOMAIN_JS, timeout_sec=30.0, page_url=security_url)
        assert local_domain.get("ready") is True, local_domain

        control_plane = wait_for_state(client, page, CONTROL_PLANE_JS, timeout_sec=30.0, page_url=security_url)
        assert control_plane.get("ready") is True, control_plane

        api_url = get_e2e_api_url()
        endpoints = seed_live_e2e_providers(api_url)
        provider_id = infer_provider_id(endpoints.basic_model)
        assert wait_e2e_provider_ready(timeout_sec=90.0), (
            f"WebUI provider store not ready after seeding {endpoints.basic_model!r}"
        )

        client.navigate(page, security_url, timeout_ms=90_000)
        dismiss_blocking_modals(client, page, recover_url=security_url)
        wait_for_settings_layout(client, page, page_url=security_url, timeout_sec=45.0)

        provider_egress = wait_for_state(
            client,
            page,
            provider_egress_visible_js(provider_id),
            timeout_sec=60.0,
            page_url=security_url,
        )
        assert provider_egress.get("ready") is True, provider_egress
        assert provider_egress.get("hasProvider") is True, provider_egress
        assert provider_egress.get("hasCloudBadge") is True, provider_egress

        export_btn = wait_for_state(
            client,
            page,
            COMPLIANCE_EXPORT_BUTTON_JS,
            timeout_sec=30.0,
            page_url=security_url,
        )
        assert export_btn.get("ready") is True, export_btn

        clicked = client.evaluate(page, CLICK_COMPLIANCE_EXPORT_JS, timeout_sec=15.0)
        assert clicked.get("ok") is True, clicked

        export_feedback = wait_for_state(client, page, EXPORT_FEEDBACK_JS, timeout_sec=60.0, page_url=security_url)
        assert export_feedback.get("ready") is True, export_feedback
        assert export_feedback.get("failed") is not True, export_feedback
        assert export_feedback.get("success") is True, export_feedback
