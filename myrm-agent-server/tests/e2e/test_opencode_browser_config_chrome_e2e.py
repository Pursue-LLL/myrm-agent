"""Chrome MCP E2E: Configure OpenCode Go provider and Muse Spark model in WebUI Settings."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
)
from tests.support.e2e_runtime_guard import heartbeat_once

_OPENCODE_API_KEY = "sk-bQTJ2yZDiY7iQI8xUWKRbRWkl5HZWVuL0Gya2gYdj3LwxvhfqbRXo8HJGfweNt67"
_OPENCODE_MODEL = "muse-spark-1.3-contributor"
_OPENCODE_PROVIDER_ID = "opencode_go"

_SETTINGS_MODELS_SHELL_STATE = """(() => {
  try {
    const bodyText = document.body?.innerText || '';
    return {
      ready:
        location.pathname.includes('/settings/models') &&
        bodyText.length > 20 &&
        !!document.querySelector('[data-testid="settings-layout"]'),
      pathname: location.pathname,
      bodyLength: bodyText.length,
    };
  } catch (err) {
    return {
      ready: false,
      pathname: location.pathname,
      bodyLength: 0,
      err: String(err),
    };
  }
})()"""

_CONFIGURE_OPENCODE_IN_PAGE_JS = f"""(async () => {{
  try {{
    const res = await fetch('/api/v1/config/providers', {{ cache: 'no-store' }});
    if (!res.ok) {{
      return {{ ok: false, step: 'fetch_failed', status: res.status }};
    }}
    const current = (await res.json())?.value || {{}};
    const providers = current.providers || [];

    let found = false;
    const updatedProviders = providers.map((p) => {{
      if (p.id === '{_OPENCODE_PROVIDER_ID}') {{
        found = true;
        const enabled = Array.from(new Set([...(p.enabledModels || []), '{_OPENCODE_MODEL}']));
        const available = Array.from(new Set([...(p.availableModels || []), '{_OPENCODE_MODEL}']));
        return {{
          ...p,
          isEnabled: true,
          apiUrl: 'https://opencode.ai/zen/go/v1',
          apiKeys: [{{ key: '{_OPENCODE_API_KEY}', isActive: true }}],
          enabledModels: enabled,
          availableModels: available,
        }};
      }}
      return p;
    }});

    if (!found) {{
      updatedProviders.push({{
        id: '{_OPENCODE_PROVIDER_ID}',
        name: 'OpenCode Go',
        isBuiltIn: true,
        isEnabled: true,
        apiUrl: 'https://opencode.ai/zen/go/v1',
        apiKeys: [{{ key: '{_OPENCODE_API_KEY}', isActive: true }}],
        enabledModels: ['{_OPENCODE_MODEL}'],
        availableModels: ['{_OPENCODE_MODEL}'],
        routingProfile: '{_OPENCODE_PROVIDER_ID}',
      }});
    }}

    const dmc = current.defaultModelConfig || {{}};
    dmc.baseModel = {{
      primary: {{ providerId: '{_OPENCODE_PROVIDER_ID}', model: '{_OPENCODE_MODEL}' }},
      fallback: null,
      temperature: 0.7,
      modelKwargs: {{}},
    }};

    const payload = {{
      ...current,
      providers: updatedProviders,
      defaultModelConfig: dmc,
    }};

    const putRes = await fetch('/api/v1/config/providers', {{
      method: 'PUT',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        deviceId: 'tauri-local',
        value: payload,
      }}),
    }});

    if (!putRes.ok) {{
      return {{ ok: false, step: 'save_providers_failed', status: putRes.status }};
    }}

    try {{
      localStorage.setItem('model-service-selected-provider', '{_OPENCODE_PROVIDER_ID}');
    }} catch (e) {{}}

    return {{ ok: true }};
  }} catch (err) {{
    return {{ ok: false, error: String(err) }};
  }}
}})()"""

_SELECT_OPENCODE_PROVIDER_JS = f"""(() => {{
  try {{
    const buttons = Array.from(document.querySelectorAll('button, div[role="button"]'));
    const opencodeBtn = buttons.find((btn) => btn.textContent && btn.textContent.includes('OpenCode Go'));
    if (opencodeBtn) {{
      opencodeBtn.click();
      return {{ clicked: true }};
    }}
    return {{ clicked: false }};
  }} catch (err) {{
    return {{ clicked: false, err: String(err) }};
  }}
}})()"""

_VERIFY_UI_RENDERED_STATE = f"""(() => {{
  try {{
    const bodyText = document.body?.innerText || '';
    const hasOpenCode = bodyText.includes('OpenCode') || bodyText.includes('opencode');
    return {{
      ready: location.pathname.includes('/settings/models') && hasOpenCode,
      hasOpenCode,
      bodySnippet: bodyText.slice(0, 300),
    }};
  }} catch (err) {{
    return {{ ready: false, err: String(err) }};
  }}
}})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_opencode_browser_config_in_webui() -> None:
    """Configures OpenCode Go provider and Muse Spark model in WebUI via real Chrome."""
    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)

    with open_settings_subroute("/settings/models") as (client, page):
        # 1. 验证 Settings 页面正常渲染
        state = wait_for_state(
            client,
            page,
            _SETTINGS_MODELS_SHELL_STATE,
            timeout_sec=min(90.0, _warm_ui_parallel_wait_sec(45.0)),
            page_url=f"{get_e2e_ui_url().rstrip('/')}/settings/models",
            blank_heal_mode="direct",
        )
        assert state.get("ready") is True, f"Settings page not ready: {state}"
        heartbeat_once()

        # 2. 在 WebUI 页面上下文中配置 OpenCode Go 与 Muse Spark 1.3 Contributor
        save_res = client.evaluate(page, _CONFIGURE_OPENCODE_IN_PAGE_JS, timeout_sec=60.0, await_promise=True)
        assert isinstance(save_res, dict) and save_res.get("ok") is True, f"Failed to configure OpenCode Go in WebUI: {save_res}"
        heartbeat_once()

        # 3. 刷新页面同步最新配置
        client.reload(page, timeout_ms=60_000)

        # 4. 等待重新加载渲染完成
        reloaded_state = wait_for_state(
            client,
            page,
            _VERIFY_UI_RENDERED_STATE,
            timeout_sec=min(60.0, _warm_ui_parallel_wait_sec(30.0)),
        )
        assert reloaded_state.get("ready") is True, f"Reloaded page verification failed: {reloaded_state}"
        heartbeat_once()

        # 5. 确保选中 OpenCode Go 提供商卡片展示其详情
        client.evaluate(page, _SELECT_OPENCODE_PROVIDER_JS, timeout_sec=15.0)

    # 7. 验证后端持久化状态
    raw_saved = http_json("GET", f"{api_base}/api/v1/config/providers")
    assert isinstance(raw_saved, dict), f"Expected dict response: {raw_saved}"
    value = raw_saved.get("value") or {}
    assert isinstance(value, dict), f"Expected dict value: {value}"
    provider_list = value.get("providers") or []
    assert isinstance(provider_list, list), f"Expected list providers: {provider_list}"
    opencode_cfg = next((p for p in provider_list if isinstance(p, dict) and p.get("id") == _OPENCODE_PROVIDER_ID), None)
    assert opencode_cfg is not None, "opencode_go provider not found in saved config"
    assert opencode_cfg.get("isEnabled") is True, "opencode_go is not enabled"
    assert _OPENCODE_MODEL in (opencode_cfg.get("enabledModels") or []), f"{_OPENCODE_MODEL} not enabled"

    dmc = value.get("defaultModelConfig") or {}
    base_model = dmc.get("baseModel") or {} if isinstance(dmc, dict) else {}
    assert isinstance(base_model, dict)
    primary = base_model.get("primary") or {}
    assert isinstance(primary, dict)
    assert primary.get("providerId") == _OPENCODE_PROVIDER_ID
    assert primary.get("model") == _OPENCODE_MODEL
