/**
 * [INPUT]
 * - @/store/useAgentStore (POS: 智能体花名册与当前详情)
 * - @/store/chat/useSubagentStore::markStale (POS: 子智能体停滞标记)
 * - ./syncBoundChatAgentConfig (POS: 把变更同步到绑定该智能体的会话)
 * - ./scheduleDebounced (POS: 事件成串到达时只刷新一次)
 *
 * [OUTPUT]
 * - agentEventHandlers: 子智能体停滞 / 需要重新绑定 / 智能体配置变更事件的处理器表
 *
 * [POS]
 * 全局事件中与智能体相关的部分：配置变更后刷新花名册与绑定会话，子智能体异常时提示用户。
 */
import { syncBoundChatAgentConfig } from '@/hooks/globalEvents/syncBoundChatAgentConfig';

import type { GlobalEventHandler } from './eventTypes';
import { scheduleDebounced } from './scheduleDebounced';

const AGENT_CONFIG_REFRESH_DELAY_MS = 500;

/** Actions of `agent_config_updated` after which the roster and the bound chat must be reloaded. */
const REFRESHING_AGENT_ACTIONS: ReadonlySet<string> = new Set(['updated', 'rollback', 'force_push']);

const handleSubagentStale: GlobalEventHandler = (payload, { t, pushToast, notifyIfLeader }) => {
  const taskId = String(payload.data.task_id ?? '');
  const staleDuration =
    typeof payload.data.stale_duration_seconds === 'number' ? payload.data.stale_duration_seconds : 0;
  const wastedTokens = typeof payload.data.wasted_tokens === 'number' ? payload.data.wasted_tokens : 0;
  const durationMin = Math.round(staleDuration / 60);
  if (taskId) {
    import('@/store/chat/useSubagentStore').then(({ useSubagentStore }) => {
      useSubagentStore.getState().markStale(taskId, staleDuration, wastedTokens);
    });
  }
  pushToast.warning(t('subagentStale'), {
    description: t('subagentStaleDescription', { minutes: durationMin, tokens: wastedTokens }),
    duration: 15_000,
    dismissible: true,
  });
  notifyIfLeader(t('subagentStale'), t('subagentStaleStats', { minutes: durationMin, tokens: wastedTokens }));
};

const handleSubagentRebindRequired: GlobalEventHandler = (_payload, { t, pushToast }) => {
  pushToast.info(t('subagentRebindRequired'), {
    duration: 10_000,
  });
};

const handleAgentConfigUpdated: GlobalEventHandler = (payload, { t, router, pushToast, debouncedRefetches }) => {
  const agentId = String(payload.data.agent_id ?? '');
  const action = String(payload.data.action ?? 'updated');
  if (agentId && REFRESHING_AGENT_ACTIONS.has(action)) {
    if (action === 'rollback') {
      pushToast.success(t('agentProfileRollbackSuccess'));
    } else if (action === 'force_push') {
      pushToast.info(t('forcePushReceived'), {
        description: t('forcePushRollbackHint'),
        duration: 10_000,
        dismissible: true,
        action: {
          label: t('viewAgent'),
          onClick: () => router.push(`/?agent_id=${agentId}`),
        },
      });
    }

    scheduleDebounced(debouncedRefetches, agentId, AGENT_CONFIG_REFRESH_DELAY_MS, () => {
      void syncBoundChatAgentConfig(agentId).catch(() => {});
      import('@/store/useAgentStore')
        .then((mod) => {
          const store = mod.default.getState();
          store.fetchAgents(true);
          if (store.selectedAgent?.id === agentId) {
            store.fetchAgent(agentId);
          }
        })
        .catch(() => {});
    });
  }
  window.dispatchEvent(new CustomEvent('agent-config-updated', { detail: payload.data }));
};

export const agentEventHandlers: Record<string, GlobalEventHandler> = {
  subagent_stale: handleSubagentStale,
  subagent_rebind_required: handleSubagentRebindRequired,
  agent_config_updated: handleAgentConfigUpdated,
};
