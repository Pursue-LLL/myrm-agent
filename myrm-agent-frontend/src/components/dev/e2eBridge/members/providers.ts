/**
 * [INPUT]
 * - @/store/chat/messageRequest::getModelSelection, getRoutingModelSelections (POS: Facade of the chat message request layer.)
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/useProviderStore::useProviderStore
 * - @/store/useConfigStore::useConfigStore
 * - @/lib/deploy-mode::getApiBaseUrl (POS: 前端部署模式与基础地址解析层。)
 * - @/lib/model-binding::isModelAvailable (POS: 模型绑定解析层：根据 actionMode 与智能体配置解析应使用的模型，优先级链为 模式/智能体绑定 > 全局默认；路由判定委托 model-routing。)
 * - @/components/dev/e2eBridge/e2eChatBridgeSendPolicy::shouldPreserveE2eActionMode, shouldRunPrepareAutomationSend (POS: Action-mode policy of an automated send: fast mode reaches the server as it is, agent-mode sends may be prepared.)
 * - @/services/config/ConfigSyncManager::getConfigSyncManager
 * - @/components/dev/e2eBridge/sendTurnContract::SEND_TURN_REV (POS: 发送回合中与 Python 端 dev_gate 契约逐值对应的常量)
 * - @/components/dev/e2eBridge/providerBootstrap::clearSearchServicesForE2e, fetchE2eProviderConfigBody, hydrateSearchServicesFromE2eApi, initProvidersForE2e (POS: 开发桥的 provider 与搜索服务引导)
 * - @/components/dev/e2eBridge/hostEnv::prepareAutomationSend, resolveE2eApiBase (POS: 开发桥的页面环境探针)
 * - @/components/dev/e2eBridge/members/types::E2eBridgeMembers (POS: 桥成员分组的类型)
 *
 * [OUTPUT]
 * - createProviderMembers(): send readiness, search-service mirroring and provider/security debug reads
 * - pinLiteModelForE2e: bind agent chat to defaultModelConfig.liteModel (API E2E parity)
 * - pinBasicModelForE2e: bind desktop E2E to defaultModelConfig.baseModel (mimo SSOT)
 * - releaseAgentModelPinForE2e: clear the agent's pinned model so the turn is smart-routed like a default user's
 *
 * [POS]
 * 桥成员（provider 与模型）：发送就绪、搜索服务镜像、provider 与安全调试读数，以及 lite/base 模型绑定。
 */
import { flushSync } from 'react-dom';
import { getModelSelection, getRoutingModelSelections } from '@/store/chat/messageRequest';
import useChatStore from '@/store/useChatStore';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';
import { getApiBaseUrl } from '@/lib/deploy-mode';
import { isModelAvailable } from '@/lib/model-binding';
import {
  shouldPreserveE2eActionMode,
  shouldRunPrepareAutomationSend,
} from '@/components/dev/e2eBridge/e2eChatBridgeSendPolicy';
import { getConfigSyncManager } from '@/services/config/ConfigSyncManager';
import { SEND_TURN_REV } from '@/components/dev/e2eBridge/sendTurnContract';
import {
  clearSearchServicesForE2e,
  fetchE2eProviderConfigBody,
  hydrateSearchServicesFromE2eApi,
  initProvidersForE2e,
} from '@/components/dev/e2eBridge/providerBootstrap';
import { prepareAutomationSend, resolveE2eApiBase } from '@/components/dev/e2eBridge/hostEnv';
import type { E2eBridgeMembers } from '@/components/dev/e2eBridge/members/types';

export function createProviderMembers(): E2eBridgeMembers {
  return {
    __e2eFallback: false,
    sendTurnRev: () => SEND_TURN_REV,
    ensureProviders: initProvidersForE2e,
    prepareAutomationSend,
    isProvidersInitialized: () => useProviderStore.getState().isInitialized,
    isSendReady: () => {
      if (!useProviderStore.getState().isInitialized) {
        return false;
      }
      const { actionMode, agentConfig } = useChatStore.getState();
      return getModelSelection(actionMode, agentConfig) !== null;
    },
    syncSearchServicesFromE2eApi: hydrateSearchServicesFromE2eApi,
    clearSearchServicesForE2e,
    debugSearchState: () => {
      const configs = useConfigStore.getState().searchServiceConfigs;
      const enabled = configs.filter((item) => item.enabled);
      return {
        count: configs.length,
        enabledCount: enabled.length,
        blockSearchSync: Boolean(window.__MYRM_E2E_BLOCK_SEARCH_SYNC__),
      };
    },
    debugSecurityState: () => {
      const syncManager = getConfigSyncManager();
      const securityConfig = syncManager.get('securityConfig');
      const { securityPreset, agentConfig } = useChatStore.getState();
      return {
        securityPreset,
        boundAgentId: agentConfig?.agentId ?? null,
        yoloModeEnabled: securityConfig?.yoloModeEnabled ?? null,
        configInitialized: syncManager.isInitialized,
        hasSecurityConfig: securityConfig !== null && securityConfig !== undefined,
      };
    },
    debugProviderState: () => {
      const { isInitialized, providers, defaultModelConfig } = useProviderStore.getState();
      const { actionMode, agentConfig, chatId, currentSessionMessageId } = useChatStore.getState();
      const selection = getModelSelection(actionMode, agentConfig);
      const lightSelection = getRoutingModelSelections(actionMode, agentConfig).light;
      return {
        isInitialized,
        actionMode,
        chatId,
        streamRequestMessageId: currentSessionMessageId?.trim() || null,
        providerIds: providers.map((p) => p.id),
        enabledProviderIds: providers.filter((p) => p.isEnabled).map((p) => p.id),
        primary: defaultModelConfig?.baseModel?.primary ?? null,
        agentModelSelection: agentConfig?.modelSelection ?? null,
        selection: selection ? { providerId: selection.providerId, model: selection.model } : null,
        routing: {
          agentHasRouting: Boolean(agentConfig?.routingConfig),
          agentRoutingEnabled: agentConfig?.routingConfig?.enabled ?? null,
          dmcHasRouting: Boolean(defaultModelConfig?.routingConfig),
          dmcRoutingEnabled: defaultModelConfig?.routingConfig?.enabled ?? null,
          dmcLightPrimary: defaultModelConfig?.routingConfig?.lightModel?.primary ?? null,
          lightSelection: lightSelection
            ? { providerId: lightSelection.providerId, model: lightSelection.model }
            : null,
        },
      };
    },
    pinLiteModelForE2e: async (opts?: { preserveActionMode?: boolean }) => {
      const preserveActionMode = shouldPreserveE2eActionMode(
        useChatStore.getState().actionMode,
        Boolean(opts?.preserveActionMode),
      );
      await initProvidersForE2e(preserveActionMode ? { preserveActionMode: true } : undefined);
      if (shouldRunPrepareAutomationSend(preserveActionMode)) {
        prepareAutomationSend();
      }
      // 与 pinBasicModelForE2e 一致：用后端权威配置校验，绕开 store 缓存。
      const authoritative = await fetchE2eProviderConfigBody();
      const serverProviders = authoritative.providers ?? [];
      const serverLitePrimary = authoritative.defaultModelConfig?.liteModel?.primary;
      const storeLitePrimary = useProviderStore.getState().defaultModelConfig?.liteModel?.primary;
      const litePrimary = serverLitePrimary ?? storeLitePrimary;
      if (!litePrimary?.providerId || !litePrimary?.model) {
        throw new Error('e2e-lite-model-unconfigured');
      }
      if (!isModelAvailable(litePrimary, serverProviders)) {
        throw new Error(`e2e-lite-model-unavailable:${litePrimary.providerId}/${litePrimary.model}`);
      }
      const authoritativeConfig = authoritative.defaultModelConfig;
      if (serverProviders.length > 0 || authoritativeConfig) {
        useProviderStore.setState({
          providers: serverProviders.length > 0 ? serverProviders : useProviderStore.getState().providers,
          defaultModelConfig: authoritativeConfig ?? useProviderStore.getState().defaultModelConfig,
        });
      }
      const selection = {
        providerId: litePrimary.providerId,
        model: litePrimary.model,
      };
      flushSync(() => {
        useProviderStore.getState().setFastModeModel(selection);
        const chat = useChatStore.getState();
        if (chat.agentConfig) {
          chat.updateAgentConfig({
            modelSelection: selection,
            enabledBuiltinTools: [...chat.currentBuiltinTools],
          });
          return;
        }
        chat.setAgentConfig({
          modelSelection: selection,
          enabledBuiltinTools: [...chat.currentBuiltinTools],
          selectedSkillIds: [],
          selectedMcpNames: [],
          systemPrompt: '',
          useGlobalInstruction: true,
        });
      });
      return selection;
    },
    pinBasicModelForE2e: async () => {
      // Desktop approval E2E requires tool-capable agent mode; fast/deep can keep send disabled
      // when search configs are intentionally empty under e2e_search_policy("empty").
      prepareAutomationSend();
      await initProvidersForE2e();
      // E2E 权威配置：直接读后端 /api/v1/config/providers，绕开 store 缓存，
      // 保证并行/共享 attach 复用页面时能看到测试 seed 的 corrupt primary。
      const authoritative = await fetchE2eProviderConfigBody();
      const serverProviders = authoritative.providers ?? [];
      const serverBasePrimary = authoritative.defaultModelConfig?.baseModel?.primary;
      const storeBasePrimary = useProviderStore.getState().defaultModelConfig?.baseModel?.primary;
      const primary = serverBasePrimary ?? storeBasePrimary;
      if (!primary?.providerId || !primary?.model) {
        throw new Error('e2e-base-model-unconfigured');
      }
      if (!isModelAvailable(primary, serverProviders)) {
        const base = (resolveE2eApiBase() || getApiBaseUrl()).replace(/\/+$/, '');
        const provider = serverProviders.find((p) => p.id === primary.providerId);
        throw new Error(
          `e2e-base-model-unavailable:${primary.providerId}/${primary.model}` +
            ` base=${base} providerId=${provider?.id ?? '?'} models=${JSON.stringify(provider?.enabledModels ?? [])}`,
        );
      }
      // 用后端权威数据刷新 store（providers + defaultModelConfig），
      // 保证后续发送走测试 seed 的 corrupt primary。
      const authoritativeConfig = authoritative.defaultModelConfig;
      if (serverProviders.length > 0 || authoritativeConfig) {
        useProviderStore.setState({
          providers: serverProviders.length > 0 ? serverProviders : useProviderStore.getState().providers,
          defaultModelConfig: authoritativeConfig ?? useProviderStore.getState().defaultModelConfig,
        });
      }
      const selection = {
        providerId: primary.providerId,
        model: primary.model,
      };
      flushSync(() => {
        useProviderStore.getState().setFastModeModel(selection);
        const chat = useChatStore.getState();
        if (chat.agentConfig) {
          chat.updateAgentConfig({
            modelSelection: selection,
            enabledBuiltinTools: [...chat.currentBuiltinTools],
          });
          return;
        }
        chat.setAgentConfig({
          modelSelection: selection,
          enabledBuiltinTools: [...chat.currentBuiltinTools],
          selectedSkillIds: [],
          selectedMcpNames: [],
          systemPrompt: '',
          useGlobalInstruction: true,
        });
      });
      return selection;
    },
    releaseAgentModelPinForE2e: () => {
      // A pinned agent opts out of smart routing; routing E2E drops the pin after binding providers.
      flushSync(() => {
        useChatStore.getState().updateAgentConfig({ modelSelection: null });
      });
    },
  } as E2eBridgeMembers;
}
