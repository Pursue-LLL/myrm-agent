/**
 * [INPUT]
 * - None (pure TypeScript type contracts)
 *
 * [OUTPUT]
 * - DashboardSpec, KpiMetric, ChartConfig, ChartSeries, TableSpec, InteractiveDashboardArtifactProps
 *
 * [POS]
 * Domain types for ZeroPromptAutonomousVisualizationAndDynamicWebDashboardEngine (Item 49 P1).
 * Strictly under 80 lines. Zero `any`.
 */

export type KpiTrend = 'up' | 'down' | 'neutral';

export interface KpiMetric {
  label: string;
  value: string;
  change_pct?: number | null;
  trend?: KpiTrend;
  detail?: string;
}

export interface ChartSeries {
  name: string;
  data: number[];
  color?: string;
}

export interface ChartConfig {
  id: string;
  title: string;
  chart_type: 'line' | 'bar' | 'pie' | 'area';
  x_axis_labels: string[];
  series: ChartSeries[];
  description?: string;
}

export interface TableSpec {
  title: string;
  headers: string[];
  rows: string[][];
  total_rows?: number;
}

export interface DashboardSpec {
  title: string;
  subtitle?: string;
  kpis: KpiMetric[];
  charts: ChartConfig[];
  tables: TableSpec[];
  theme?: string;
  timestamp?: number;
}

export interface InteractiveDashboardArtifactProps {
  content: string;
  title?: string;
  filename?: string;
  className?: string;
  onDownloadHtml?: () => void;
}
