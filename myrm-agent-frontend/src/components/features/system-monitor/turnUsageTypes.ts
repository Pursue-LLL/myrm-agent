/**
 * [INPUT]: Turn usage summary, billed vs freeze dual counters, and round simulation parameters.
 * [OUTPUT]: Strong TypeScript definitions for Turn Billed Usage Dual Count HUD.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/turnUsageTypes.ts
 */

export interface NormalizedUsageData {
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_read?: number | null;
  cache_write?: number | null;
}

export interface TurnUsageSummaryData {
  session_id: string;
  turn_id: string;
  rounds_count: number;
  billed: NormalizedUsageData;
  freeze_usage: NormalizedUsageData;
  cache_divergence_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface TurnBilledUsageDualCountHUDProps {
  summary: TurnUsageSummaryData;
  onRefresh?: () => void;
  onSimulateRound?: (roundUsage: NormalizedUsageData) => Promise<void> | void;
}
