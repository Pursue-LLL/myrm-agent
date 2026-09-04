/**
 * [INPUT]
 * - None (pure type declarations)
 *
 * [OUTPUT]
 * - SignificanceVerdict, PlateauMechanism, McNemarData, BootstrapCIData, PlateauData, ContinuousMetricsDelta, PairedSignificanceData
 *
 * [POS]
 * - Type definitions for paired statistical significance evaluation in Eval Lab Matrix view
 */

export type SignificanceVerdict =
  | 'significant_improvement'
  | 'significant_regression'
  | 'efficiency_breakthrough'
  | 'no_significant_difference'
  | 'insufficient_discordance';

export type PlateauMechanism =
  | 'insufficient_power'
  | 'capability_saturation'
  | 'cross_model_divergence'
  | 'hard_subset_bottleneck'
  | 'none';

export interface McNemarData {
  statistic: number;
  p_value: number;
  is_significant: boolean;
  contingency_table: {
    both_pass: number;
    base_only: number;
    cand_only: number;
    both_fail: number;
  };
  test_type: 'exact_binomial' | 'edwards_continuity_chi2' | 'no_discordant_pairs';
}

export interface BootstrapCIData {
  ci_lower: number;
  ci_upper: number;
  delta_mean: number;
  confidence_level: number;
  sample_runs: number;
  crosses_zero: boolean;
}

export interface PlateauData {
  mechanism: PlateauMechanism;
  title: string;
  explanation: string;
  recommendation: string;
  suggested_action: string;
}

export interface ContinuousMetricsDelta {
  token_diff_pct: number;
  token_ci_95: [number, number];
  cost_diff_pct: number;
  cost_ci_95: [number, number];
  latency_diff_pct: number;
  latency_ci_95: [number, number];
}

export interface PairedSignificanceData {
  base_id: string;
  candidate_id: string;
  base_pass_rate: number;
  candidate_pass_rate: number;
  delta_pass_rate: number;
  mcnemar: McNemarData;
  bootstrap_ci: BootstrapCIData;
  plateau: PlateauData;
  verdict: SignificanceVerdict;
  regression_case_indices: number[];
  improved_case_indices: number[];
  continuous_delta?: ContinuousMetricsDelta | null;
}
