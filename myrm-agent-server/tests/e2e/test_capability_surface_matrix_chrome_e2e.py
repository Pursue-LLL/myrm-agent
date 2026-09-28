"""Chrome MCP E2E: CapabilitySurface Always/Ask/Deny Permission Matrix WebUI Suite.

Covers the full real-user workflow in the WebUI Settings Security tab:
1. Shell & Matrix mount — navigating to /settings/security hydrates and renders
   the 6-surface CapabilitySurfaceMatrixGrid with action controls.
2. User tri-state action switch — clicking Allow/Ask/Deny on a specific surface
   (e.g., knowledge_write -> deny) updates UI and persists to backend config.
3. Posture presets batch application — clicking Guarded/Autonomous presets batch
   updates all 6 capability surfaces and persists atomically.
4. Fail-closed backend parity — queries /api/v1/config/securityConfig to verify
   that the capabilityMatrix state is persisted with high-fidelity parity.
"""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_allowlist_settings_e2e import SETTINGS_SECURITY_SHELL_READY_JS
from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)

_MATRIX_MOUNT_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const grid = document.querySelector('[data-testid="capability-matrix-grid"]');
  if (!grid) {
    return {
      ready: false,
      err: 'no-grid',
      url: location.href,
      bodySnippet: text.slice(0, 300),
      hasSecurityHeading: /Security Policy|安全策略/.test(text),
    };
  }
  const surfaces = [
    'knowledge_read',
    'knowledge_write',
    'web_egress',
    'candidate_create',
    'remote_tools',
    'local_filesystem',
  ];
  const missing = surfaces.filter(
    (key) => !document.querySelector(`[data-testid="capability-surface-card-${key}"]`),
  );
  return {
    ready: missing.length === 0,
    missing,
    cardsCount: grid.children.length,
    url: location.href,
  };
})()"""

_CLICK_KNOWLEDGE_WRITE_DENY_JS = """(() => {
  const btn = document.querySelector('[data-testid="capability-action-knowledge_write-deny"]');
  if (!btn) return { ok: false, err: 'no-knowledge-write-deny-btn' };
  btn.click();
  return { ok: true };
})()"""

_KNOWLEDGE_WRITE_DENY_ACTIVE_JS = """(() => {
  const btn = document.querySelector('[data-testid="capability-action-knowledge_write-deny"]');
  if (!btn) return { ready: false };
  const isActive = btn.className.includes('bg-destructive');
  return { ready: isActive, isActive };
})()"""

_CLICK_AUTONOMOUS_PRESET_JS = """(() => {
  const btn = document.querySelector('[data-testid="capability-preset-geek"]');
  if (!btn) return { ok: false, err: 'no-autonomous-preset-btn' };
  btn.click();
  return { ok: true };
})()"""

_AUTONOMOUS_PRESET_ACTIVE_JS = """(() => {
  const surfaces = [
    'knowledge_read',
    'knowledge_write',
    'web_egress',
    'candidate_create',
    'local_filesystem',
  ];
  const allAllow = surfaces.every((key) => {
    const btn = document.querySelector(`[data-testid="capability-action-${key}-allow"]`);
    return btn && btn.className.includes('bg-emerald-500');
  });
  const remoteToolsAsk = document.querySelector('[data-testid="capability-action-remote_tools-ask"]');
  const isRemoteAsk = remoteToolsAsk && remoteToolsAsk.className.includes('bg-amber-500');
  return { ready: Boolean(allAllow && isRemoteAsk) };
})()"""

_CLICK_GUARDED_PRESET_JS = """(() => {
  const btn = document.querySelector('[data-testid="capability-preset-guarded"]');
  if (!btn) return { ok: false, err: 'no-guarded-preset-btn' };
  btn.click();
  return { ok: true };
})()"""

_GUARDED_PRESET_ACTIVE_JS = """(() => {
  const remoteToolsDeny = document.querySelector('[data-testid="capability-action-remote_tools-deny"]');
  const webEgressAsk = document.querySelector('[data-testid="capability-action-web_egress-ask"]');
  const isRemoteDeny = remoteToolsDeny && remoteToolsDeny.className.includes('bg-destructive');
  const isWebAsk = webEgressAsk && webEgressAsk.className.includes('bg-amber-500');
  return { ready: Boolean(isRemoteDeny && isWebAsk) };
})()"""

_CLICK_BALANCED_PRESET_JS = """(() => {
  const btn = document.querySelector('[data-testid="capability-preset-balanced"]');
  if (!btn) return { ok: false, err: 'no-balanced-preset-btn' };
  btn.click();
  return { ok: true };
})()"""

_BALANCED_PRESET_ACTIVE_JS = """(() => {
  const kwAsk = document.querySelector('[data-testid="capability-action-knowledge_write-ask"]');
  const isKwAsk = kwAsk && kwAsk.className.includes('bg-amber-500');
  return { ready: Boolean(isKwAsk) };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.timeout(300)
def test_capability_surface_matrix_chrome_e2e() -> None:
    """Real-user E2E workflow: verify CapabilitySurface Always/Ask/Deny matrix."""
    api_base = get_e2e_api_url()
    warm_ui_route("/settings/security")

    with open_settings_subroute("/settings/security", timeout_ms=90_000) as (client, page):
        # 0. 先等待 Settings Security 外层 Shell 水合就绪
        shell_state = wait_for_state(client, page, SETTINGS_SECURITY_SHELL_READY_JS, timeout_sec=90.0)
        assert shell_state.get("ready") is True, f"Shell not ready: {json.dumps(shell_state)}"

        # 1. 验证能力面矩阵卡片及 6 大能力面网格完全加载挂载
        mount_state = wait_for_state(client, page, _MATRIX_MOUNT_READY_JS, timeout_sec=60.0)
        assert mount_state.get("ready") is True, f"Matrix failed to mount: {json.dumps(mount_state)}"
        assert mount_state.get("cardsCount", 0) >= 6

        # 2. 模拟真实用户点击切换单个能力面：将 knowledge_write 切换为 Deny
        deny_click = client.evaluate(page, _CLICK_KNOWLEDGE_WRITE_DENY_JS, timeout_sec=15.0)
        assert isinstance(deny_click, dict) and deny_click.get("ok") is True, deny_click

        deny_active = wait_for_state(client, page, _KNOWLEDGE_WRITE_DENY_ACTIVE_JS, timeout_sec=20.0)
        assert deny_active.get("ready") is True, f"Deny button not active: {json.dumps(deny_active)}"

        # 3. 模拟真实用户点击预设：应用 Autonomous (全自动放行) 预设
        auto_click = client.evaluate(page, _CLICK_AUTONOMOUS_PRESET_JS, timeout_sec=15.0)
        assert isinstance(auto_click, dict) and auto_click.get("ok") is True, auto_click

        auto_active = wait_for_state(client, page, _AUTONOMOUS_PRESET_ACTIVE_JS, timeout_sec=20.0)
        assert auto_active.get("ready") is True, f"Autonomous preset not active: {json.dumps(auto_active)}"

        # 4. 模拟真实用户点击预设：应用 Guarded (谨慎防范) 预设
        guarded_click = client.evaluate(page, _CLICK_GUARDED_PRESET_JS, timeout_sec=15.0)
        assert isinstance(guarded_click, dict) and guarded_click.get("ok") is True, guarded_click

        guarded_active = wait_for_state(client, page, _GUARDED_PRESET_ACTIVE_JS, timeout_sec=20.0)
        assert guarded_active.get("ready") is True, f"Guarded preset not active: {json.dumps(guarded_active)}"

        # 5. 校验后端配置接口返回数据落盘一致性（轮询等待异步落盘）
        deadline = time.monotonic() + 20.0
        matrix: dict[str, object] = {}
        while time.monotonic() < deadline:
            res: dict[str, object] = http_json("GET", f"{api_base}/api/v1/config/securityConfig")
            cfg_val = res.get("value") if isinstance(res, dict) and "value" in res else res
            if isinstance(cfg_val, dict):
                m = cfg_val.get("capabilityMatrix")
                if isinstance(m, dict) and m.get("remote_tools") == "deny":
                    matrix = m
                    break
            time.sleep(0.5)

        assert matrix.get("remote_tools") == "deny", f"remote_tools not deny in backend: {matrix}"
        assert matrix.get("web_egress") == "ask", f"web_egress not ask in backend: {matrix}"

        # 6. 环境恢复与清理：重置为 Balanced 预设，避免污染其他测试
        client.evaluate(page, _CLICK_BALANCED_PRESET_JS, timeout_sec=15.0)
        wait_for_state(client, page, _BALANCED_PRESET_ACTIVE_JS, timeout_sec=20.0)

        # 等待 Balanced 预设落盘完成
        reset_deadline = time.monotonic() + 10.0
        while time.monotonic() < reset_deadline:
            res = http_json("GET", f"{api_base}/api/v1/config/securityConfig")
            cfg_val = res.get("value") if isinstance(res, dict) and "value" in res else res
            if isinstance(cfg_val, dict):
                m = cfg_val.get("capabilityMatrix")
                if isinstance(m, dict) and m.get("knowledge_write") == "ask" and m.get("remote_tools") == "ask":
                    break
            time.sleep(0.5)
