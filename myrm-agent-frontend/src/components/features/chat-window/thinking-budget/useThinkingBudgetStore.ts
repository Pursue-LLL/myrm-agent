'use client';

import { create } from 'zustand';
import {
  ReasoningStage,
  ThinkingBudgetLevel,
} from './thinkingBudgetTypes';
import { parseReasoningStages } from './reasoningTimelineEngine';

export interface ThinkingBudgetState {
  currentBudgetLevel: ThinkingBudgetLevel;
  isThinkingCapable: boolean;
  isSelectorOpen: boolean;

  // 消息气泡思维链内联状态
  isThinking: boolean;
  isExpanded: boolean;
  totalElapsedSec: number;
  thinkingTokens: number;
  rawContent: string;
  stages: ReasoningStage[];

  setBudgetLevel: (level: ThinkingBudgetLevel) => void;
  setIsThinkingCapable: (capable: boolean) => void;
  toggleSelector: (open?: boolean) => void;
  toggleExpanded: (expanded?: boolean) => void;
  startThinking: () => void;
  appendThinkingChunk: (chunk: string, tokenDelta?: number, elapsedSec?: number) => void;
  finishThinking: () => void;
  reset: () => void;
}

const DEFAULT_COT_SAMPLE = `[阶段 1: 意图解构与边界定义]
用户需要设计高并发网关架构与分布式鉴权机制。首先确认业务峰值 QPS 为 50,000，核心要求为 99.99% 可用性与低于 10ms 的 p99 延迟。

[阶段 2: 方案推演与对抗验证]
权衡集中式 Redis 集群与本地基于 eBPF 的无锁缓存网关。集中式方案在极端抖动时可能出现网络级联故障，因此采用轻量级边缘节点 + 异步批量上报机制更具备弹性。

[阶段 3: 最优架构确认与执行落地]
最终决定采用分层熔断与自适应令牌桶限流算法，配合零拷贝网络栈，确保吞吐量与故障就地自愈能力。`;

const INITIAL_STAGES = parseReasoningStages(DEFAULT_COT_SAMPLE, false);

export const useThinkingBudgetStore = create<ThinkingBudgetState>((set, get) => ({
  currentBudgetLevel: 'medium',
  isThinkingCapable: true,
  isSelectorOpen: false,

  isThinking: false,
  isExpanded: false,
  totalElapsedSec: 14.8,
  thinkingTokens: 4210,
  rawContent: DEFAULT_COT_SAMPLE,
  stages: INITIAL_STAGES,

  setBudgetLevel: (level: ThinkingBudgetLevel) => {
    set({ currentBudgetLevel: level, isSelectorOpen: false });
  },

  setIsThinkingCapable: (capable: boolean) => {
    set({ isThinkingCapable: capable });
  },

  toggleSelector: (open?: boolean) => {
    set((state) => ({
      isSelectorOpen: open !== undefined ? open : !state.isSelectorOpen,
    }));
  },

  toggleExpanded: (expanded?: boolean) => {
    set((state) => ({
      isExpanded: expanded !== undefined ? expanded : !state.isExpanded,
    }));
  },

  startThinking: () => {
    set({
      isThinking: true,
      isExpanded: false,
      totalElapsedSec: 0,
      thinkingTokens: 0,
      rawContent: '',
      stages: [],
    });
  },

  appendThinkingChunk: (chunk: string, tokenDelta: number = 4, elapsedSec?: number) => {
    set((state) => {
      const nextContent = state.rawContent + chunk;
      const nextStages = parseReasoningStages(nextContent, true);
      const nextTokens = state.thinkingTokens + tokenDelta;
      const nextElapsed = elapsedSec !== undefined ? elapsedSec : Number((state.totalElapsedSec + 0.2).toFixed(1));

      return {
        rawContent: nextContent,
        stages: nextStages,
        thinkingTokens: nextTokens,
        totalElapsedSec: nextElapsed,
      };
    });
  },

  finishThinking: () => {
    const { rawContent } = get();
    const finalizedStages = parseReasoningStages(rawContent, false);
    set({
      isThinking: false,
      stages: finalizedStages,
    });
  },

  reset: () => {
    set({
      currentBudgetLevel: 'medium',
      isThinkingCapable: true,
      isSelectorOpen: false,
      isThinking: false,
      isExpanded: false,
      totalElapsedSec: 14.8,
      thinkingTokens: 4210,
      rawContent: DEFAULT_COT_SAMPLE,
      stages: INITIAL_STAGES,
    });
  },
}));
