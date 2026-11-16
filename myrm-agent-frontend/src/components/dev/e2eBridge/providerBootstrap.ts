/**
 * [INPUT]
 * - @/store/chat/messageRequest::getModelSelection (POS: Facade of the chat message request layer.)
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/useProviderStore::useProviderStore
 * - @/store/useConfigStore::useConfigStore
 * - @/store/config/types::SearchServiceConfigItem
 * - @/store/config/providerTypes::CustomModelInfo, DefaultModelConfig, ProviderConfig
 * - @/store/chat/types::ActionMode, AgentConfig (POS: @/store/chat/types 稳定入口；实现位于 types/。)
 * - @/lib/backend-health::markLocalBackendUnreachable (POS: Backend readiness facade.)
 * - @/lib/deploy-mode::getApiBaseUrl (POS: 前端部署模式与基础地址解析层。)
 * - @/lib/platform-readiness::markPlatformUnreachable (POS: Frontend-only coordinator.)
 * - @/components/dev/e2eBridge/e2eChatBridgeSendPolicy::shouldPreserveE2eActionMode, shouldRunPrepareAutomationSend (POS: Action-mode policy of an automated send: fast mode reaches the server as it is, agent-mode sends may be prepared.)
 * - @/services/config/ConfigSyncManager::getConfigSyncManager
 * - @/components/dev/e2eBridge/hostEnv::prepareAutomationSend, resolveE2eApiBase (POS: 开发桥的页面环境探针)
 *
 * [OUTPUT]
 * - initProvidersForE2e(opts): refresh the provider store from the authoritative backend config, then wait until a model selection resolves
 * - isE2eProviderSendReady / waitE2eProviderSendReady: getModelSelection SSOT (lite or base) as the send-readiness probe
 * - probePrivateBackendReady: the injected backend answers `/api/v1/health` and reports a ready database on `/api/v1/health/ready`
 * - fetchE2eProviderConfigBody: authoritative `/api/v1/config/providers` body, bypassing the session cache
 * - hydrateSearchServicesFromE2eApi / clearSearchServicesForE2e: mirror or empty the search-service configs in the config store
 *
 * [POS]
 * 开发桥的 provider 与搜索服务引导：以后端权威配置刷新前端 store，等待模型选择就绪，并管理 E2E 的搜索服务镜像。
 */
import { getModelSelection } from '@/store/chat/messageRequest';
import useChatStore from '@/store/useChatStore';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';
import type { SearchServiceConfigItem } from '@/store/config/types';
import type { CustomModelInfo, DefaultModelConfig, ProviderConfig } from '@/store/config/providerTypes';
import type { ActionMode, AgentConfig } from '@/store/chat/types';
import { markLocalBackendUnreachable } from '@/lib/backend-health';
import { getApiBaseUrl } from '@/lib/deploy-mode';
import { markPlatformUnreachable } from '@/lib/platform-readiness';
import {
  shouldPreserveE2eActionMode,
  shouldRunPrepareAutomationSend,
} from '@/components/dev/e2eBridge/e2eChatBridgeSendPolicy';
import { getConfigSyncManager } from '@/services/config/ConfigSyncManager';
import { prepareAutomationSend, resolveE2eApiBase } from '@/components/dev/e2eBridge/hostEnv';

function isE2eProviderSendReady(actionMode: ActionMode, agentConfig: AgentConfig | null): boolean {
  const refreshed = useProviderStore.getState();
  if (!refreshed.isInitialized) {
    return false;
  }
  return getModelSelection(actionMode, agentConfig) !== null;
}

async function waitE2eProviderSendReady(deadlineMs: number, preserveActionMode = false): Promise<void> {
  while (Date.now() < deadlineMs) {
    if (!preserveActionMode) {
      prepareAutomationSend();
    }
    const { actionMode, agentConfig } = useChatStore.getState();
    if (isE2eProviderSendReady(actionMode, agentConfig)) {
      return;
    }
    const refreshed = useProviderStore.getState();
    if (!refreshed.isInitialized) {
      await useProviderStore.getState().initProviders();
    } else {
      await useProviderStore.getState().retryInit();
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error('e2e-send-not-ready-after-provider-init');
}

function extractSearchServiceConfigs(body: unknown): SearchServiceConfigItem[] {
  if (!body || typeof body !== 'object') {
    return [];
  }
  const record = body as { value?: { searchServiceConfigs?: unknown }; searchServiceConfigs?: unknown };
  const root =
    record.value && typeof record.value === 'object' ? record.value : (record as { searchServiceConfigs?: unknown });
  const configs = root.searchServiceConfigs;
  return Array.isArray(configs) ? (configs as SearchServiceConfigItem[]) : [];
}

async function fetchSearchServiceConfigsFromApi(apiBase: string): Promise<SearchServiceConfigItem[]> {
  const normalizedApi = apiBase.replace(/\/+$/, '');
  try {
    const resp = await fetch(`${normalizedApi}/api/v1/config/searchServices`, { cache: 'no-store' });
    if (!resp.ok) {
      return [];
    }
    const body: unknown = await resp.json();
    return extractSearchServiceConfigs(body);
  } catch {
    return [];
  }
}

export function clearSearchServicesForE2e(): { ok: boolean; count: number } {
  window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
  useConfigStore.setState({ searchServiceConfigs: [] });
  try {
    getConfigSyncManager().set('searchServices', { searchServiceConfigs: [] });
  } catch {
    /* cache-only mirror when sync manager unavailable */
  }
  return { ok: true, count: 0 };
}

export async function hydrateSearchServicesFromE2eApi(): Promise<{ ok: boolean; err?: string; count?: number }> {
  try {
    const e2eApiBase = resolveE2eApiBase();
    if (!e2eApiBase) {
      return { ok: false, err: 'no-e2e-api-base' };
    }
    const blockSearchSync = typeof window !== 'undefined' && window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
    const configs = blockSearchSync ? [] : await fetchSearchServiceConfigsFromApi(e2eApiBase);
    useConfigStore.setState({ searchServiceConfigs: configs });
    return { ok: true, count: configs.length };
  } catch {
    return { ok: false, err: 'empty-search-configs' };
  }
}

async function probePrivateBackendReady(e2eApiBase: string): Promise<boolean> {
  try {
    const health = await fetch(`${e2eApiBase}/api/v1/health`, { cache: 'no-store' });
    if (!health.ok) {
      return false;
    }
    const ready = await fetch(`${e2eApiBase}/api/v1/health/ready`, { cache: 'no-store' });
    if (!ready.ok) {
      return false;
    }
    const body = (await ready.json()) as { checks?: { database?: boolean } };
    return body.checks?.database === true;
  } catch {
    return false;
  }
}

type E2eProviderConfigBody = {
  value?: {
    providers?: ProviderConfig[];
    defaultModelConfig?: DefaultModelConfig;
    customModelInfo?: Record<string, CustomModelInfo>;
  };
  providers?: ProviderConfig[];
  defaultModelConfig?: DefaultModelConfig;
  customModelInfo?: Record<string, CustomModelInfo>;
};

/**
 * E2E 权威配置读取：直接请求后端 /api/v1/config/providers，
 * 绕开 ConfigSyncManager 会话级缓存，避免测试 seed（PRIVATE runtime
 * 并行复用时 upsert 的 corrupt primary）不被前端感知。
 */
export async function fetchE2eProviderConfigBody(): Promise<E2eProviderConfigBody> {
  // `getApiBaseUrl()` already ends in `/api/v1`; only the injected E2E base is a bare origin.
  const rawBase = resolveE2eApiBase() || getApiBaseUrl();
  const apiBase = rawBase.replace(/\/+$/, '').replace(/\/api\/v1$/, '');
  const res = await fetch(`${apiBase}/api/v1/config/providers`, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`e2e-provider-config-fetch-${res.status}`);
  }
  const body = (await res.json()) as E2eProviderConfigBody;
  const value = (body.value ?? body) as E2eProviderConfigBody;
  if (typeof window !== 'undefined' && window.__MYRM_E2E_RUNTIME__) {
    console.log(
      '[E2EChatBridge] authoritative providers base=%s primary=%s/%s count=%d',
      apiBase,
      value.defaultModelConfig?.baseModel?.primary?.providerId ?? '?',
      value.defaultModelConfig?.baseModel?.primary?.model ?? '?',
      value.providers?.length ?? 0,
    );
  }
  return value;
}

export type E2eChatSessionOpts = { preserveActionMode?: boolean };

export async function initProvidersForE2e(opts?: E2eChatSessionOpts): Promise<void> {
  const e2eApiBase = resolveE2eApiBase();
  if (e2eApiBase) {
    const preserveActionMode = shouldPreserveE2eActionMode(
      useChatStore.getState().actionMode,
      Boolean(opts?.preserveActionMode),
    );
    if (shouldRunPrepareAutomationSend(preserveActionMode)) {
      prepareAutomationSend();
    }
    // E2E 权威刷新：并行测试直接通过 API seed 后端 config（PRIVATE runtime 复用 /
    // 热 attach 复用页面时 ConfigSyncManager 会话缓存不感知），若前端 provider
    // store 停留在 seed 前快照，发送将不带 light_model_selection 导致后端不路由
    //（routing_decision 缺失 / routingTier=None 现场失败）。因此 E2E 发送前
    // 一律以 /api/v1/config/providers 为准刷新 store，不信任本会话陈旧缓存。
    try {
      const body = await fetchE2eProviderConfigBody();
      useProviderStore.setState((current) => ({
        providers: Array.isArray(body.providers) ? body.providers : current.providers,
        defaultModelConfig: body.defaultModelConfig ?? current.defaultModelConfig,
        customModelInfo: body.customModelInfo ?? current.customModelInfo ?? {},
        isInitialized: true,
      }));
    } catch {
      // 后端暂不可达时保留现状，走原有 probe/retry 路径
    }
    const { actionMode, agentConfig } = useChatStore.getState();
    if (isE2eProviderSendReady(actionMode, agentConfig)) {
      return;
    }

    markPlatformUnreachable();
    markLocalBackendUnreachable();
    const normalizedApi = e2eApiBase.replace(/\/+$/, '');
    const workspaceStatus = typeof window !== 'undefined' ? window.__MYRM_WORKSPACE_STREAM_STATUS__?.() : undefined;
    const workspaceConnected =
      workspaceStatus?.connected === true && (workspaceStatus.origin ?? '').replace(/\/+$/, '') === normalizedApi;

    const deadline = Date.now() + 120_000;
    let ready = false;
    while (Date.now() < deadline) {
      if (await probePrivateBackendReady(e2eApiBase)) {
        ready = true;
        break;
      }
      if (workspaceConnected) {
        try {
          const health = await fetch(`${normalizedApi}/api/v1/health`, { cache: 'no-store' });
          if (health.ok) {
            ready = true;
            break;
          }
        } catch {
          // retry until deadline
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (!ready) {
      throw new Error('e2e-private-backend-not-ready');
    }
    await useProviderStore.getState().retryInit();
    if (typeof window !== 'undefined' && window.__MYRM_E2E_BLOCK_SEARCH_SYNC__) {
      clearSearchServicesForE2e();
    } else {
      await hydrateSearchServicesFromE2eApi();
    }
    await waitE2eProviderSendReady(Date.now() + 120_000, preserveActionMode);
    return;
  }
  const providerState = useProviderStore.getState();
  if (!providerState.isInitialized) {
    await providerState.initProviders();
  }
  const preserveActionMode = shouldPreserveE2eActionMode(useChatStore.getState().actionMode, false);
  await waitE2eProviderSendReady(Date.now() + 120_000, preserveActionMode);
}
