"""Scripts that write the pinned config from the chat page.

[INPUT]
- e2e_core.dev_ports::shared_api_base (POS: default ports of the user, shared dev and isolated stacks)

[OUTPUT]
- CLEAR_E2E_CONFIG_OFFLINE_QUEUE_JS: drop the queued offline config writes of the page, whichever account queued them
- PUT_E2E_CLEAR_SEARCH_CONFIG_JS, PUT_E2E_YOLO_CONFIG_JS, PUT_E2E_HITL_CONFIG_JS: PUT the pinned config through the page

[POS]
Scripts that write the pinned config through the page's own API layer and clear its offline queues.
"""

from __future__ import annotations

from e2e_core.dev_ports import shared_api_base

# Every signed-in account keeps its own offline queue under `config-offline-queue:<userId>`; a session whose token
# names no account uses the bare `config-offline-queue` key.
_DROP_OFFLINE_QUEUES_JS = """Object.keys(localStorage)
      .filter((key) => key === 'config-offline-queue' || key.startsWith('config-offline-queue:'))
      .forEach((key) => localStorage.removeItem(key));"""

CLEAR_E2E_CONFIG_OFFLINE_QUEUE_JS = """(() => {
  try {
    __DROP_OFFLINE_QUEUES__
  } catch (_) {}
  return { ok: true };
})()""".replace("__DROP_OFFLINE_QUEUES__", _DROP_OFFLINE_QUEUES_JS)

PUT_E2E_CLEAR_SEARCH_CONFIG_JS = """(async () => {
  const privateApi = String(window.__MYRM_E2E_API_BASE__ || '').replace(/\\/+$/, '');
  if (!privateApi) {
    return { ok: false, err: 'no-api-base' };
  }
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const mirrorStore = async () => {
    window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
    try {
      const useConfigStore = (await import('/src/store/useConfigStore')).default;
      useConfigStore.setState({ searchServiceConfigs: [] });
    } catch (_) {
      /* optional FE store mirror */
    }
    try {
      const { getConfigSyncManager } = await import('@/services/config/ConfigSyncManager');
      getConfigSyncManager().set('searchServices', { searchServiceConfigs: [] });
    } catch (_) {
      /* cache-only mirror when sync import unavailable */
    }
  };
  const verifyEmpty = async () => {
    const verifyResp = await fetch(`${privateApi}/api/v1/config/searchServices`, { cache: 'no-store' });
    if (!verifyResp.ok) {
      return { ok: false, err: `fetch-${verifyResp.status}` };
    }
    const body = await verifyResp.json();
    const persisted = body?.value ?? body?.data?.value ?? body?.data ?? {};
    const configs = Array.isArray(persisted?.searchServiceConfigs)
      ? persisted.searchServiceConfigs
      : [];
    return { ok: configs.length === 0, configCount: configs.length };
  };
  try {
    __DROP_OFFLINE_QUEUES__
    window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
    const value = { searchServiceConfigs: [] };
    let lastPutStatus = 0;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const putResp = await fetch(`${privateApi}/api/v1/config/searchServices`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deviceId: 'web', value }),
        cache: 'no-store',
      });
      lastPutStatus = putResp.status;
      if (putResp.ok) {
        const verified = await verifyEmpty();
        await mirrorStore();
        return {
          ok: verified.ok === true,
          mode: 'put-ok',
          configCount: verified.configCount ?? null,
          err: verified.err ?? null,
        };
      }
      if (putResp.status >= 500 && attempt < 2) {
        await sleep(250 * (attempt + 1));
        continue;
      }
      break;
    }
    const verified = await verifyEmpty();
    if (verified.ok === true) {
      await mirrorStore();
      return {
        ok: true,
        mode: 'verify-fallback',
        putStatus: lastPutStatus,
        configCount: verified.configCount ?? 0,
      };
    }
    return {
      ok: false,
      err: lastPutStatus ? `put-${lastPutStatus}` : 'put-failed',
      configCount: verified.configCount ?? null,
      verifyErr: verified.err ?? null,
    };
  } catch (error) {
    return { ok: false, err: String(error) };
  }
})()""".replace("__DROP_OFFLINE_QUEUES__", _DROP_OFFLINE_QUEUES_JS)

PUT_E2E_YOLO_CONFIG_JS = """(async () => {
  const privateApi = String(window.__MYRM_E2E_API_BASE__ || '').replace(/\\/+$/, '');
  const sharedApi = '__SHARED_API_BASE__';
  const targets = [...new Set([privateApi, sharedApi].filter(Boolean))];
  if (targets.length === 0) {
    return { ok: false, err: 'no-api-base' };
  }
  try {
    __DROP_OFFLINE_QUEUES__
    const nowSec = Math.floor(Date.now() / 1000);
    const value = {
      yoloModeEnabled: true,
      yoloModeEnabledAt: nowSec,
      yoloModeTimeout: null,
      yolo_mode_enabled: true,
      yolo_mode_enabled_at: nowSec,
      yolo_mode_timeout: null,
      autoModeEnabled: true,
      autoReviewEnabled: false,
      planConfirmEnabled: false,
      domainHitlEnabled: false,
      permissions: { '*': 'allow', computer_use: 'allow' },
    };
    const results = [];
    for (const api of targets) {
      const putResp = await fetch(`${api}/api/v1/config/securityConfig`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deviceId: 'web', value }),
        cache: 'no-store',
      });
      if (!putResp.ok) {
        results.push({ api, ok: false, err: `put-${putResp.status}` });
        continue;
      }
      const verifyResp = await fetch(`${api}/api/v1/config/securityConfig`, { cache: 'no-store' });
      if (!verifyResp.ok) {
        results.push({ api, ok: false, err: `fetch-${verifyResp.status}` });
        continue;
      }
      const body = await verifyResp.json();
      const persisted = body?.value ?? body?.data?.value ?? body?.data ?? {};
      const yolo = Boolean(persisted?.yoloModeEnabled || persisted?.yolo_mode_enabled);
      const perms = persisted?.permissions;
      const computerUseAllow =
        typeof perms === 'object' &&
        perms !== null &&
        (String(perms['computer_use'] || '').toLowerCase() === 'allow' ||
          String(perms['*'] || '').toLowerCase() === 'allow');
      results.push({
        api,
        ok: yolo && computerUseAllow,
        yoloModeEnabled: yolo,
        computerUseAllow,
      });
    }
    try {
      const { getConfigSyncManager } = await import('@/services/config/ConfigSyncManager');
      getConfigSyncManager().set('securityConfig', value);
    } catch (_) {
      /* E2E pin still valid via server PUT when local sync import fails */
    }
    return {
      ok: results.every((row) => row.ok),
      results,
    };
  } catch (error) {
    return { ok: false, err: String(error), targets };
  }
})()""".replace("__SHARED_API_BASE__", shared_api_base()).replace("__DROP_OFFLINE_QUEUES__", _DROP_OFFLINE_QUEUES_JS)

PUT_E2E_HITL_CONFIG_JS = """(async () => {
  const privateApi = String(window.__MYRM_E2E_API_BASE__ || '').replace(/\\/+$/, '');
  const sharedApi = '__SHARED_API_BASE__';
  const targets = [...new Set([privateApi, sharedApi].filter(Boolean))];
  if (targets.length === 0) {
    return { ok: false, err: 'no-api-base' };
  }
  try {
    __DROP_OFFLINE_QUEUES__
    const value = {
      yoloModeEnabled: false,
      yoloModeEnabledAt: null,
      yoloModeTimeout: null,
      yolo_mode_enabled: false,
      yolo_mode_enabled_at: null,
      yolo_mode_timeout: null,
      autoModeEnabled: false,
      autoReviewEnabled: false,
      planConfirmEnabled: false,
      domainHitlEnabled: false,
      approvalTimeoutBehavior: 'deny',
      permissions: { shell_exec: 'ask', code_interpreter: 'ask', computer_use: 'ask' },
    };
    const results = [];
    for (const api of targets) {
      const putResp = await fetch(`${api}/api/v1/config/securityConfig`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deviceId: 'web', value }),
        cache: 'no-store',
      });
      if (!putResp.ok) {
        results.push({ api, ok: false, err: `put-${putResp.status}` });
        continue;
      }
      const verifyResp = await fetch(`${api}/api/v1/config/securityConfig`, { cache: 'no-store' });
      if (!verifyResp.ok) {
        results.push({ api, ok: false, err: `fetch-${verifyResp.status}` });
        continue;
      }
      const body = await verifyResp.json();
      const persisted = body?.value ?? body?.data?.value ?? body?.data ?? {};
      const yolo = Boolean(persisted?.yoloModeEnabled || persisted?.yolo_mode_enabled);
      const perms = persisted?.permissions;
      const wildcardAllow =
        typeof perms === 'object' &&
        perms !== null &&
        String(perms['*'] || '').toLowerCase() === 'allow';
      const computerUseAsk =
        typeof perms === 'object' &&
        perms !== null &&
        String(perms['computer_use'] || '').toLowerCase() === 'ask';
      results.push({
        api,
        ok: !yolo && !wildcardAllow && computerUseAsk,
        yoloModeEnabled: yolo,
        wildcardAllow,
        computerUseAsk,
      });
    }
    try {
      const { getConfigSyncManager } = await import('@/services/config/ConfigSyncManager');
      getConfigSyncManager().set('securityConfig', value);
    } catch (_) {
      /* E2E pin still valid via server PUT when local sync import fails */
    }
    return {
      ok: results.every((row) => row.ok),
      results,
    };
  } catch (error) {
    return { ok: false, err: String(error), targets };
  }
})()""".replace("__SHARED_API_BASE__", shared_api_base()).replace("__DROP_OFFLINE_QUEUES__", _DROP_OFFLINE_QUEUES_JS)
