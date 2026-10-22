'use client';

import { create } from 'zustand';
import {
  AgentTokenCostProfile,
  ChatSnapshotThrottleConfig,
  StreamingPatch,
  ThrottleMetrics,
} from './granularCostTypes';
import {
  calculateAgentCost,
  createThrottledSnapshotEngine,
} from './chatSnapshotThrottleEngine';

export interface AgentGranularCostState {
  agentProfiles: AgentTokenCostProfile[];
  activeHoveredAgentId: string | null;
  throttleConfig: ChatSnapshotThrottleConfig;
  currentStreamBuffer: string;
  throttleMetrics: ThrottleMetrics;

  setActiveHoveredAgentId: (agentId: string | null) => void;
  recordAgentUsage: (
    agentId: string,
    promptDelta: number,
    completionDelta: number,
    cachedDelta?: number
  ) => void;
  dispatchStreamingChunk: (agentId: string, patch: StreamingPatch) => void;
  flushStreamingBuffer: (agentId: string) => void;
  updateThrottleConfig: (partial: Partial<ChatSnapshotThrottleConfig>) => void;
  reset: () => void;
}

const INITIAL_PROFILES: AgentTokenCostProfile[] = [
  {
    agentId: 'agent-planner',
    agentName: '架构规划专家 (Planner)',
    role: '系统顶层解构与分步任务编排',
    avatarIconName: 'BrainCircuit',
    promptTokens: 42500,
    completionTokens: 8200,
    cachedTokens: 12000,
    totalTokens: 50700,
    estimatedCostUsd: 0.082,
    costRate: { prompt: 0.0015, completion: 0.002 },
    historyPoints: [
      { timestamp: 1, tokens: 12000, cost: 0.018 },
      { timestamp: 2, tokens: 18500, cost: 0.031 },
      { timestamp: 3, tokens: 20200, cost: 0.033 },
    ],
  },
  {
    agentId: 'agent-coder',
    agentName: '全栈工程工匠 (Coder)',
    role: '高性能前端/后端核心组件落地',
    avatarIconName: 'Code2',
    promptTokens: 86400,
    completionTokens: 24600,
    cachedTokens: 35000,
    totalTokens: 111000,
    estimatedCostUsd: 0.179,
    costRate: { prompt: 0.0015, completion: 0.002 },
    historyPoints: [
      { timestamp: 1, tokens: 32000, cost: 0.051 },
      { timestamp: 2, tokens: 41000, cost: 0.066 },
      { timestamp: 3, tokens: 38000, cost: 0.062 },
    ],
  },
  {
    agentId: 'agent-reviewer',
    agentName: '代码极度严苛审查员 (Reviewer)',
    role: '静态代码门禁与质量红线防线',
    avatarIconName: 'ShieldAlert',
    promptTokens: 19800,
    completionTokens: 3400,
    cachedTokens: 6000,
    totalTokens: 23200,
    estimatedCostUsd: 0.036,
    costRate: { prompt: 0.0015, completion: 0.002 },
    historyPoints: [
      { timestamp: 1, tokens: 8000, cost: 0.012 },
      { timestamp: 2, tokens: 7200, cost: 0.011 },
      { timestamp: 3, tokens: 8000, cost: 0.013 },
    ],
  },
];

let globalThrottleEngine = createThrottledSnapshotEngine({
  throttleMs: 300,
  maxPendingPatches: 20,
});

export const useAgentGranularCostStore = create<AgentGranularCostState>((set, get) => ({
  agentProfiles: INITIAL_PROFILES,
  activeHoveredAgentId: null,
  throttleConfig: { throttleMs: 300, maxPendingPatches: 20 },
  currentStreamBuffer: '',
  throttleMetrics: {
    totalPatchesReceived: 0,
    snapshotsCommitted: 0,
    redundantSnapshotsPrevented: 0,
    reductionRatePercentage: 0,
  },

  setActiveHoveredAgentId: (agentId: string | null) => {
    set({ activeHoveredAgentId: agentId });
  },

  recordAgentUsage: (
    agentId: string,
    promptDelta: number,
    completionDelta: number,
    cachedDelta: number = 0
  ) => {
    set((state) => {
      const updatedProfiles = state.agentProfiles.map((p) => {
        if (p.agentId !== agentId) {
          return p;
        }

        const newPrompt = p.promptTokens + promptDelta;
        const newCompletion = p.completionTokens + completionDelta;
        const newCached = p.cachedTokens + cachedDelta;
        const newTotal = newPrompt + newCompletion;
        const newCost = calculateAgentCost(newPrompt, newCompletion, p.costRate);

        const newPoint = {
          timestamp: Date.now(),
          tokens: promptDelta + completionDelta,
          cost: calculateAgentCost(promptDelta, completionDelta, p.costRate),
        };

        const updatedHistory = [...p.historyPoints.slice(-9), newPoint];

        return {
          ...p,
          promptTokens: newPrompt,
          completionTokens: newCompletion,
          cachedTokens: newCached,
          totalTokens: newTotal,
          estimatedCostUsd: newCost,
          historyPoints: updatedHistory,
        };
      });

      return { agentProfiles: updatedProfiles };
    });
  },

  dispatchStreamingChunk: (agentId: string, patch: StreamingPatch) => {
    globalThrottleEngine.queuePatch(patch, (combinedText, totalTokens) => {
      // 聚合冲刷：统一提交快照
      set((state) => ({
        currentStreamBuffer: state.currentStreamBuffer + combinedText,
        throttleMetrics: globalThrottleEngine.getMetrics(),
      }));

      get().recordAgentUsage(agentId, 0, totalTokens);
    });

    set({ throttleMetrics: globalThrottleEngine.getMetrics() });
  },

  flushStreamingBuffer: (agentId: string) => {
    globalThrottleEngine.flush((combinedText, totalTokens) => {
      set((state) => ({
        currentStreamBuffer: state.currentStreamBuffer + combinedText,
        throttleMetrics: globalThrottleEngine.getMetrics(),
      }));
      get().recordAgentUsage(agentId, 0, totalTokens);
    });
  },

  updateThrottleConfig: (partial: Partial<ChatSnapshotThrottleConfig>) => {
    set((state) => {
      const nextConfig = { ...state.throttleConfig, ...partial };
      globalThrottleEngine = createThrottledSnapshotEngine(nextConfig);
      return { throttleConfig: nextConfig };
    });
  },

  reset: () => {
    globalThrottleEngine.clear();
    set({
      agentProfiles: INITIAL_PROFILES,
      activeHoveredAgentId: null,
      currentStreamBuffer: '',
      throttleMetrics: {
        totalPatchesReceived: 0,
        snapshotsCommitted: 0,
        redundantSnapshotsPrevented: 0,
        reductionRatePercentage: 0,
      },
    });
  },
}));
