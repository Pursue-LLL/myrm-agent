/**
 * [INPUT]: Context breakdown snapshot, seven-category shares, and alert levels.
 * [OUTPUT]: Strong TypeScript definitions for WorkBuddy Context Usage Breakdown HUD.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/contextBreakdownTypes.ts
 */

export type ContextAlertLevel = 'NORMAL' | 'WARNING_60' | 'CRITICAL_90';

export interface ContextCategoryShareData {
  category: string;
  label_zh: string;
  estimated_tokens: number;
  percentage: number;
  color_hex: string;
}

export interface ContextBreakdownData {
  total_window_tokens: number;
  provider_actual_tokens: number;
  estimated_sum_tokens: number;
  usage_ratio_pct: number;
  alert_level: ContextAlertLevel;
  alert_message: string;
  categories: Record<string, ContextCategoryShareData>;
}

export interface ContextUsageBreakdownHUDProps {
  data: ContextBreakdownData;
  onRefresh?: () => void;
  onTriggerCompact?: () => Promise<void> | void;
  isCompacting?: boolean;
}
