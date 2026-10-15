/**
 * Provider Quota & Telemetry Types
 * 多渠道模型提供商实时配额、余额与遥测状态机定义
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 字段完备语义化。
 */

export type ProviderId =
  | 'nous'
  | 'openai'
  | 'anthropic'
  | 'openrouter'
  | 'deepseek'
  | 'local';

export type QuotaStatusLevel =
  | 'healthy'
  | 'warning'
  | 'critical'
  | 'exhausted';

export interface ProviderQuotaSnapshot {
  id: ProviderId;
  name: string;
  modelIdentifier: string;
  totalTokensLimit: number;
  remainingTokens: number;
  remainingPercentage: number;
  balanceUsd: number;
  initialDepositUsd: number;
  dailyBurnRateUsd: number;
  resetWindowSeconds: number;
  lastUpdatedTimestamp: number;
  status: QuotaStatusLevel;
  supportsLiveTelemetry: boolean;
}

export interface ModelUsageDistribution {
  modelName: string;
  tokenCount: number;
  percentage: number;
  estimatedCostUsd: number;
}

export interface AgentRoleUsage {
  agentRole: string;
  taskCount: number;
  tokenCount: number;
  costUsd: number;
}

export interface DailyUsageTrendPoint {
  date: string;
  tokensConsumed: number;
  costUsd: number;
}

export interface ProviderFailoverAction {
  sourceProviderId: ProviderId;
  targetProviderId: ProviderId;
  reason: 'insufficient_quota' | 'rate_limit_exceeded' | 'manual_switch';
  timestamp: number;
  sessionSuspended: boolean;
}
