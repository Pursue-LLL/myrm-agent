'use client';

export type TimeRangeKey = '7d' | '30d' | '90d';

export type GatewayHealthStatus = 'healthy' | 'degraded' | 'offline';

export type DiagnosticCategory = 'gateway' | 'sandbox' | 'storage' | 'security';

export type DiagnosticStatus = 'pass' | 'warning' | 'error';

export interface DiagnosticCheckItem {
  id: string;
  category: DiagnosticCategory;
  name: string;
  status: DiagnosticStatus;
  detail: string;
  remediable: boolean;
  isFixing?: boolean;
}

export interface TopModelStat {
  modelId: string;
  name: string;
  tokens: number;
  percentage: number;
}

export interface TopSkillStat {
  skillId: string;
  name: string;
  invocationCount: number;
}

export interface DailySpendPoint {
  day: string;
  tokens: number;
  cost: number;
}

export interface UsageSpendSummary {
  period: TimeRangeKey;
  totalTokens: number;
  estimatedCostUsd: number;
  dailyTrend: DailySpendPoint[];
  topModels: TopModelStat[];
  topSkills: TopSkillStat[];
}

export interface PinnedWorkstream {
  id: string;
  title: string;
  lastActive: string;
  category: 'chat' | 'workflow' | 'artifact';
  isPinned: boolean;
}
