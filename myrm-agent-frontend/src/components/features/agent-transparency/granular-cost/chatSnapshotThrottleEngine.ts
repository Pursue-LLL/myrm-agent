'use client';

import {
  ChatSnapshotThrottleConfig,
  StreamingPatch,
  ThrottleMetrics,
  TokenCostRate,
} from './granularCostTypes';

/**
 * 精确计算 Token 产生的折算成本
 */
export function calculateAgentCost(
  promptTokens: number,
  completionTokens: number,
  rate: TokenCostRate
): number {
  const promptCost = (promptTokens / 1000) * rate.prompt;
  const completionCost = (completionTokens / 1000) * rate.completion;
  return Number((promptCost + completionCost).toFixed(4));
}

/**
 * 格式化展示 Token 数量（如 32.4k / 1.2M）
 */
export function formatTokenCount(tokens: number): string {
  if (tokens >= 1_000_000) {
    return `${(tokens / 1_000_000).toFixed(1)}M`;
  }
  if (tokens >= 1_000) {
    return `${(tokens / 1_000).toFixed(1)}k`;
  }
  return String(tokens);
}

/**
 * 格式化美金金额
 */
export function formatCostUsd(cost: number): string {
  if (cost === 0) {
    return '$0.00';
  }
  if (cost < 0.001) {
    return '< $0.001';
  }
  const rounded = (Math.round((cost + Number.EPSILON) * 1000) / 1000).toFixed(3);
  return `$${rounded}`;
}

/**
 * 会话状态防抖节流快照引擎工厂
 */
export function createThrottledSnapshotEngine(
  config: ChatSnapshotThrottleConfig = { throttleMs: 300, maxPendingPatches: 20 }
) {
  let pendingPatches: StreamingPatch[] = [];
  let timerId: NodeJS.Timeout | null = null;
  let totalPatchesReceived = 0;
  let snapshotsCommitted = 0;

  const flush = (
    onBatchCommit: (accumulatedText: string, totalTokenDelta: number) => void
  ) => {
    if (timerId) {
      clearTimeout(timerId);
      timerId = null;
    }

    if (pendingPatches.length === 0) {
      return;
    }

    let combinedText = '';
    let totalTokens = 0;

    for (const patch of pendingPatches) {
      combinedText += patch.chunkText;
      totalTokens += patch.tokenDelta;
    }

    pendingPatches = [];
    snapshotsCommitted += 1;

    onBatchCommit(combinedText, totalTokens);
  };

  const queuePatch = (
    patch: StreamingPatch,
    onBatchCommit: (accumulatedText: string, totalTokenDelta: number) => void
  ) => {
    totalPatchesReceived += 1;
    pendingPatches.push(patch);

    // 若积压补丁超过设定的突发上限，立即冲刷
    if (pendingPatches.length >= config.maxPendingPatches) {
      flush(onBatchCommit);
      return;
    }

    // 若尚未设定延迟定时器，则设定 throttleMs 之后冲刷
    if (!timerId) {
      timerId = setTimeout(() => {
        timerId = null;
        flush(onBatchCommit);
      }, config.throttleMs);
    }
  };

  const getMetrics = (): ThrottleMetrics => {
    const prevented = Math.max(0, totalPatchesReceived - snapshotsCommitted);
    const reductionRate =
      totalPatchesReceived > 0
        ? Math.round((prevented / totalPatchesReceived) * 100)
        : 0;

    return {
      totalPatchesReceived,
      snapshotsCommitted,
      redundantSnapshotsPrevented: prevented,
      reductionRatePercentage: reductionRate,
    };
  };

  const clear = () => {
    if (timerId) {
      clearTimeout(timerId);
      timerId = null;
    }
    pendingPatches = [];
    totalPatchesReceived = 0;
    snapshotsCommitted = 0;
  };

  return {
    queuePatch,
    flush,
    getMetrics,
    clear,
  };
}
