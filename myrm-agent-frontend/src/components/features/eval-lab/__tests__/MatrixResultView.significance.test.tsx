// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import MatrixResultView, { type MatrixReportData } from '../components/MatrixResultView';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

function baseReportWithSignificance(): MatrixReportData {
  return {
    profile_ids: ['baseline_v1', 'candidate_v2'],
    total_cases: 4,
    stable_count: 2,
    regression_count: 1,
    stable_rate: 0.5,
    per_profile: {
      baseline_v1: {
        pass_count: 2,
        fail_count: 2,
        error_count: 0,
        pass_rate: 0.5,
        total_tokens: 1000,
        total_cost: 0.01,
        total_ms: 2000,
      },
      candidate_v2: {
        pass_count: 3,
        fail_count: 1,
        error_count: 0,
        pass_rate: 0.75,
        total_tokens: 800,
        total_cost: 0.008,
        total_ms: 1800,
      },
    },
    matrix: [
      {
        case_index: 0,
        message: 'Prompt case 0',
        profiles: {
          baseline_v1: { passed: true, total_ms: 500, token_usage: {}, cost: 0.002, error: null },
          candidate_v2: { passed: true, total_ms: 450, token_usage: {}, cost: 0.002, error: null },
        },
      },
      {
        case_index: 1,
        message: 'Prompt case 1 - regressed',
        profiles: {
          baseline_v1: { passed: true, total_ms: 500, token_usage: {}, cost: 0.002, error: null },
          candidate_v2: { passed: false, total_ms: 450, token_usage: {}, cost: 0.002, error: 'fail' },
        },
      },
      {
        case_index: 2,
        message: 'Prompt case 2 - improved',
        profiles: {
          baseline_v1: { passed: false, total_ms: 500, token_usage: {}, cost: 0.003, error: 'fail' },
          candidate_v2: { passed: true, total_ms: 450, token_usage: {}, cost: 0.002, error: null },
        },
      },
      {
        case_index: 3,
        message: 'Prompt case 3 - improved',
        profiles: {
          baseline_v1: { passed: false, total_ms: 500, token_usage: {}, cost: 0.003, error: 'fail' },
          candidate_v2: { passed: true, total_ms: 450, token_usage: {}, cost: 0.002, error: null },
        },
      },
    ],
    total_ms: 3800,
    paired_significance: {
      'baseline_v1:candidate_v2': {
        base_id: 'baseline_v1',
        candidate_id: 'candidate_v2',
        base_pass_rate: 0.5,
        candidate_pass_rate: 0.75,
        delta_pass_rate: 0.25,
        mcnemar: {
          statistic: 0.333,
          p_value: 0.625,
          is_significant: false,
          contingency_table: {
            both_pass: 1,
            base_only: 1,
            cand_only: 2,
            both_fail: 0,
          },
          test_type: 'exact_binomial',
        },
        bootstrap_ci: {
          ci_lower: -0.25,
          ci_upper: 0.5,
          delta_mean: 0.25,
          confidence_level: 0.95,
          sample_runs: 1000,
          crosses_zero: true,
        },
        plateau: {
          mechanism: 'cross_model_divergence',
          title: 'Regression Noise Divergence',
          explanation: 'New version introduced 1 regressions while difference is statistically non-significant.',
          recommendation: 'Do not adopt this variant. It trades existing baseline capability for accidental gains.',
          suggested_action: 'reject_and_investigate_regressions',
        },
        verdict: 'no_significant_difference',
        regression_case_indices: [1],
        improved_case_indices: [2, 3],
        continuous_delta: {
          token_diff_pct: -0.2,
          token_ci_95: [-0.3, -0.1],
          cost_diff_pct: -0.2,
          cost_ci_95: [-0.3, -0.1],
          latency_diff_pct: -0.1,
          latency_ci_95: [-0.2, 0.0],
        },
      },
    },
  };
}

describe('MatrixResultView Paired Significance Integration', () => {
  it('renders PairedSignificancePanel when paired_significance is provided', () => {
    const report = baseReportWithSignificance();
    render(<MatrixResultView report={report} />);

    const panel = screen.getByTestId('paired-significance-panel');
    expect(panel).toBeInTheDocument();
    expect(screen.getByText('evalLab.significance.panelTitle')).toBeInTheDocument();
    expect(screen.getByText('evalLab.significance.verdict.noSignificantDifference')).toBeInTheDocument();
    expect(screen.getByText('p = 0.6250')).toBeInTheDocument();
  });

  it('renders contingency table and plateau honest education', () => {
    const report = baseReportWithSignificance();
    render(<MatrixResultView report={report} />);

    expect(screen.getByText('evalLab.significance.contingencyTableTitle')).toBeInTheDocument();
    expect(screen.getByText('+2')).toBeInTheDocument(); // cand_only
    expect(screen.getByText('-1')).toBeInTheDocument(); // base_only
    expect(screen.getByText('Regression Noise Divergence')).toBeInTheDocument();
    expect(
      screen.getByText('evalLab.significance.suggestedActionMap.reject_and_investigate_regressions'),
    ).toBeInTheDocument();
  });

  it('filters cases when user clicks on View Regressions button', () => {
    const report = baseReportWithSignificance();
    render(<MatrixResultView report={report} />);

    // Initially all 4 cases are visible
    expect(screen.getByText('#1')).toBeInTheDocument();
    expect(screen.getByText('#2')).toBeInTheDocument();
    expect(screen.getByText('#3')).toBeInTheDocument();
    expect(screen.getByText('#4')).toBeInTheDocument();

    // Click filter regression cases button
    const regressionBtn = screen.getByText(/evalLab\.significance\.filterRegressionCases/);
    fireEvent.click(regressionBtn);

    // Only case #2 (index 1) should remain in the filtered view
    expect(screen.queryByText('#1')).toBeNull();
    expect(screen.getByText('#2')).toBeInTheDocument();
    expect(screen.queryByText('#3')).toBeNull();
    expect(screen.queryByText('#4')).toBeNull();

    // Click clear filter button
    const clearBtn = screen.getByText('evalLab.significance.clearFilter');
    fireEvent.click(clearBtn);

    // All cases restored
    expect(screen.getByText('#1')).toBeInTheDocument();
    expect(screen.getByText('#2')).toBeInTheDocument();
    expect(screen.getByText('#3')).toBeInTheDocument();
    expect(screen.getByText('#4')).toBeInTheDocument();
  });
});
