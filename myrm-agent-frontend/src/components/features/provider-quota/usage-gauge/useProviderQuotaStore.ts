/**
 * Provider Quota Store (Zustand)
 * 多渠道模型提供商实时配额、余额仪表与自愈降级状态总线
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 集中式事件广播与热恢复支持。
 */

import { create } from 'zustand';
import {
  ProviderId,
  ProviderQuotaSnapshot,
  ModelUsageDistribution,
  AgentRoleUsage,
  DailyUsageTrendPoint,
  ProviderFailoverAction,
} from './providerQuotaTypes';
import {
  getDefaultProviderSnapshots,
  parseTelemetryHeaders,
  calculateQuotaHealth,
} from './quotaTelemetryParser';

export interface ProviderQuotaState {
  providers: Record<ProviderId, ProviderQuotaSnapshot>;
  activeProviderId: ProviderId;
  isAnalyticsModalOpen: boolean;
  isExhaustionWarningOpen: boolean;
  lastFailoverAction: ProviderFailoverAction | null;
  modelDistributions: ModelUsageDistribution[];
  agentUsages: AgentRoleUsage[];
  dailyTrends: DailyUsageTrendPoint[];

  // Actions
  setActiveProvider: (id: ProviderId) => void;
  setAnalyticsModalOpen: (open: boolean) => void;
  setExhaustionWarningOpen: (open: boolean) => void;
  updateFromTelemetryHeaders: (
    providerId: ProviderId,
    headers: Record<string, string>
  ) => void;
  triggerFailoverRecovery: (
    targetProviderId: ProviderId,
    reason?: 'insufficient_quota' | 'rate_limit_exceeded' | 'manual_switch'
  ) => void;
  simulateQuotaConsumption: (tokensConsumed: number, costUsd: number) => void;
  resetToDefaults: () => void;
}

const DEFAULT_MODEL_DISTRIBUTIONS: ModelUsageDistribution[] = [
  {
    modelName: 'Nous GPT-6 Astra',
    tokenCount: 2_450_000,
    percentage: 49.0,
    estimatedCostUsd: 12.25,
  },
  {
    modelName: 'Claude 3.7 Sonnet',
    tokenCount: 1_350_000,
    percentage: 27.0,
    estimatedCostUsd: 8.1,
  },
  {
    modelName: 'DeepSeek Chat V3',
    tokenCount: 800_000,
    percentage: 16.0,
    estimatedCostUsd: 0.48,
  },
  {
    modelName: 'Local Ollama 70B',
    tokenCount: 400_000,
    percentage: 8.0,
    estimatedCostUsd: 0.0,
  },
];

const DEFAULT_AGENT_USAGES: AgentRoleUsage[] = [
  {
    agentRole: 'Architecture Reviewer',
    taskCount: 38,
    tokenCount: 2_100_000,
    costUsd: 9.8,
  },
  {
    agentRole: 'Fullstack Coder',
    taskCount: 54,
    tokenCount: 1_850_000,
    costUsd: 7.2,
  },
  {
    agentRole: 'E2E Test Verifier',
    taskCount: 29,
    tokenCount: 750_000,
    costUsd: 2.9,
  },
  {
    agentRole: 'Web Researcher',
    taskCount: 15,
    tokenCount: 300_000,
    costUsd: 0.9,
  },
];

const DEFAULT_DAILY_TRENDS: DailyUsageTrendPoint[] = [
  { date: '10-09', tokensConsumed: 620_000, costUsd: 2.8 },
  { date: '10-10', tokensConsumed: 890_000, costUsd: 4.1 },
  { date: '10-11', tokensConsumed: 740_000, costUsd: 3.3 },
  { date: '10-12', tokensConsumed: 1_120_000, costUsd: 5.2 },
  { date: '10-13', tokensConsumed: 950_000, costUsd: 4.4 },
  { date: '10-14', tokensConsumed: 1_280_000, costUsd: 5.9 },
  { date: '10-15', tokensConsumed: 480_000, costUsd: 2.1 },
];

export const useProviderQuotaStore = create<ProviderQuotaState>(
  (set, get) => ({
    providers: getDefaultProviderSnapshots(),
    activeProviderId: 'nous',
    isAnalyticsModalOpen: false,
    isExhaustionWarningOpen: false,
    lastFailoverAction: null,
    modelDistributions: DEFAULT_MODEL_DISTRIBUTIONS,
    agentUsages: DEFAULT_AGENT_USAGES,
    dailyTrends: DEFAULT_DAILY_TRENDS,

    setActiveProvider: (id: ProviderId) => {
      set({ activeProviderId: id });
      const targetProvider = get().providers[id];
      if (
        targetProvider &&
        (targetProvider.status === 'critical' ||
          targetProvider.status === 'exhausted')
      ) {
        set({ isExhaustionWarningOpen: true });
      } else {
        set({ isExhaustionWarningOpen: false });
      }
    },

    setAnalyticsModalOpen: (open: boolean) => {
      set({ isAnalyticsModalOpen: open });
    },

    setExhaustionWarningOpen: (open: boolean) => {
      set({ isExhaustionWarningOpen: open });
    },

    updateFromTelemetryHeaders: (
      providerId: ProviderId,
      headers: Record<string, string>
    ) => {
      const updates = parseTelemetryHeaders(providerId, headers);
      const current = get().providers[providerId];
      if (!current) {
        return;
      }

      const merged: ProviderQuotaSnapshot = {
        ...current,
        ...updates,
        lastUpdatedTimestamp: Date.now(),
      };

      set((state) => ({
        providers: {
          ...state.providers,
          [providerId]: merged,
        },
      }));

      // 如果当前正在使用的渠道额度耗尽或危险，主动触发预警并广播
      if (
        providerId === get().activeProviderId &&
        (merged.status === 'critical' || merged.status === 'exhausted')
      ) {
        set({ isExhaustionWarningOpen: true });
        if (typeof window !== 'undefined') {
          window.dispatchEvent(
            new CustomEvent('myrm:provider-quota-exhausted', {
              detail: { provider: merged },
            })
          );
        }
      }
    },

    triggerFailoverRecovery: (
      targetProviderId: ProviderId,
      reason = 'insufficient_quota'
    ) => {
      const sourceId = get().activeProviderId;
      const failoverAction: ProviderFailoverAction = {
        sourceProviderId: sourceId,
        targetProviderId,
        reason,
        timestamp: Date.now(),
        sessionSuspended: false,
      };

      set({
        activeProviderId: targetProviderId,
        isExhaustionWarningOpen: false,
        lastFailoverAction: failoverAction,
      });

      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('myrm:provider-failover', {
            detail: failoverAction,
          })
        );
      }
    },

    simulateQuotaConsumption: (tokensConsumed: number, costUsd: number) => {
      const activeId = get().activeProviderId;
      const current = get().providers[activeId];
      if (!current || !current.supportsLiveTelemetry) {
        return;
      }

      const nextRemainingTokens = Math.max(
        0,
        current.remainingTokens - tokensConsumed
      );
      const nextBalanceUsd = Math.max(0, current.balanceUsd - costUsd);
      const nextPercentage = Math.min(
        100,
        Math.max(
          0,
          Math.round(
            (nextRemainingTokens / current.totalTokensLimit) * 1000
          ) / 10
        )
      );

      const nextStatus = calculateQuotaHealth(
        nextPercentage,
        nextRemainingTokens
      );

      const updatedSnapshot: ProviderQuotaSnapshot = {
        ...current,
        remainingTokens: nextRemainingTokens,
        balanceUsd: Math.round(nextBalanceUsd * 100) / 100,
        remainingPercentage: nextPercentage,
        status: nextStatus,
        lastUpdatedTimestamp: Date.now(),
      };

      set((state) => ({
        providers: {
          ...state.providers,
          [activeId]: updatedSnapshot,
        },
      }));

      if (nextStatus === 'critical' || nextStatus === 'exhausted') {
        set({ isExhaustionWarningOpen: true });
      }
    },

    resetToDefaults: () => {
      set({
        providers: getDefaultProviderSnapshots(),
        activeProviderId: 'nous',
        isAnalyticsModalOpen: false,
        isExhaustionWarningOpen: false,
        lastFailoverAction: null,
        modelDistributions: DEFAULT_MODEL_DISTRIBUTIONS,
        agentUsages: DEFAULT_AGENT_USAGES,
        dailyTrends: DEFAULT_DAILY_TRENDS,
      });
    },
  })
);
