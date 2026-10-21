'use client';

export interface TokenCostRate {
  prompt: number; // 美元 / 1k tokens
  completion: number; // 美元 / 1k tokens
}

export interface UsageHistoryPoint {
  timestamp: number;
  tokens: number;
  cost: number;
}

export interface AgentTokenCostProfile {
  agentId: string;
  agentName: string;
  role: string;
  avatarIconName: string;
  promptTokens: number;
  completionTokens: number;
  cachedTokens: number;
  totalTokens: number;
  estimatedCostUsd: number;
  costRate: TokenCostRate;
  historyPoints: UsageHistoryPoint[];
}

export interface StreamingPatch {
  turnId: string;
  chunkText: string;
  tokenDelta: number;
  timestamp: number;
}

export interface ThrottleMetrics {
  totalPatchesReceived: number;
  snapshotsCommitted: number;
  redundantSnapshotsPrevented: number;
  reductionRatePercentage: number;
}

export interface ChatSnapshotThrottleConfig {
  throttleMs: number;
  maxPendingPatches: number;
}
