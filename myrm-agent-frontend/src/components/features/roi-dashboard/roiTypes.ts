/**
 * [INPUT]
 * - None (pure TypeScript type definitions)
 *
 * [OUTPUT]
 * - RoiTimeRange, CategorySavingsItem, WeeklyDigestSpec, RoiMetricsSnapshot, HighYieldRoutineSpec
 * - RoiValueDashboardCardProps, HighYieldRoutineCatalogProps
 *
 * [POS]
 * Domain types for AgentMeasurableRoiAndDailyTimeSavedHUD (Item 51 P0).
 * Strictly under 120 lines. Zero `any`.
 */

export type RoiTimeRange = 'today' | 'week' | 'all_time';

export interface CategorySavingsItem {
  category_key: string;
  label_zh: string;
  label_en: string;
  tasks_count: number;
  hours_saved: number;
  value_usd: number;
}

export interface WeeklyDigestSpec {
  week_label: string;
  total_tasks_completed: number;
  total_hours_saved: number;
  total_value_usd: number;
  total_token_cost_usd: number;
  net_roi_multiplier: number;
  top_performer_agent: string;
  prevented_errors_count: number;
}

export interface RoiMetricsSnapshot {
  time_range: RoiTimeRange;
  total_hours_saved: number;
  total_monetary_saved_usd: number;
  total_compute_cost_usd: number;
  net_roi_multiplier: number;
  hourly_rate_baseline_usd: number;
  categories_breakdown: CategorySavingsItem[];
  recent_digest?: WeeklyDigestSpec;
  generated_at?: number;
}

export interface HighYieldRoutineSpec {
  routine_id: string;
  title_zh: string;
  title_en: string;
  description_zh: string;
  description_en: string;
  estimated_minutes_saved: number;
  typical_roi_multiplier: number;
  category: string;
  preset_prompt: string;
}

export interface RoiValueDashboardCardProps {
  metrics?: RoiMetricsSnapshot;
  timeRange?: RoiTimeRange;
  onTimeRangeChange?: (range: RoiTimeRange) => void;
  onOpenDigest?: () => void;
  className?: string;
}

export interface HighYieldRoutineCatalogProps {
  routines?: HighYieldRoutineSpec[];
  onTriggerRoutine?: (routine: HighYieldRoutineSpec) => void;
  className?: string;
}
