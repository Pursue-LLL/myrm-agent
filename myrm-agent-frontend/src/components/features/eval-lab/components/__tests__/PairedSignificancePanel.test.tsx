import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import React from 'react';
import PairedSignificancePanel, { type PairedSignificanceData } from '../PairedSignificancePanel';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('PairedSignificancePanel', () => {
  const mockImprovementData: PairedSignificanceData = {
    base_id: 'prof_base',
    candidate_id: 'prof_cand',
    base_pass_rate: 0.7,
    candidate_pass_rate: 0.85,
    delta_pass_rate: 0.15,
    mcnemar: {
      statistic: 6.0,
      p_value: 0.0143,
      is_significant: true,
      contingency_table: {
        both_pass: 25,
        base_only: 2,
        cand_only: 8,
        both_fail: 5,
      },
      test_type: 'exact_binomial',
    },
    bootstrap_ci: {
      ci_lower: 0.035,
      ci_upper: 0.265,
      delta_mean: 0.15,
      confidence_level: 0.95,
      sample_runs: 1000,
      crosses_zero: false,
    },
    plateau: {
      mechanism: 'none',
      title: 'Valid Signal',
      explanation: 'Clear statistical confidence.',
      recommendation: 'Safe to proceed with adoption.',
      suggested_action: 'proceed_with_gate',
    },
    verdict: 'significant_improvement',
    regression_case_indices: [4, 18],
    improved_case_indices: [1, 7, 12, 19, 23, 28, 33, 37],
    continuous_delta: {
      token_diff_pct: -0.18,
      token_ci_95: [-0.25, -0.11],
      cost_diff_pct: -0.15,
      cost_ci_95: [-0.22, -0.08],
      latency_diff_pct: -0.12,
      latency_ci_95: [-0.19, -0.05],
    },
  };

  const mockRegressionData: PairedSignificanceData = {
    base_id: 'prof_base',
    candidate_id: 'prof_cand2',
    base_pass_rate: 0.8,
    candidate_pass_rate: 0.65,
    delta_pass_rate: -0.15,
    mcnemar: {
      statistic: 7.0,
      p_value: 0.0078,
      is_significant: true,
      contingency_table: {
        both_pass: 26,
        base_only: 6,
        cand_only: 0,
        both_fail: 8,
      },
      test_type: 'exact_binomial',
    },
    bootstrap_ci: {
      ci_lower: -0.25,
      ci_upper: -0.05,
      delta_mean: -0.15,
      confidence_level: 0.95,
      sample_runs: 1000,
      crosses_zero: false,
    },
    plateau: {
      mechanism: 'cross_model_divergence',
      title: 'Regression Noise Divergence',
      explanation: 'Introduced 6 regressions.',
      recommendation: 'Do not adopt this variant.',
      suggested_action: 'reject_and_investigate_regressions',
    },
    verdict: 'significant_regression',
    regression_case_indices: [2, 5, 11, 20, 29, 35],
    improved_case_indices: [],
  };

  const getProfileLabel = (id: string) => (id === 'prof_base' ? 'Base-v1' : id === 'prof_cand' ? 'Cand-v2' : 'Cand-v3');

  it('renders nothing if less than 2 profiles or empty paired significance', () => {
    const { container } = render(
      <PairedSignificancePanel pairedSignificance={{}} profileIds={['prof_base']} getProfileLabel={getProfileLabel} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders significant improvement panel with all statistical metrics', () => {
    render(
      <PairedSignificancePanel
        pairedSignificance={{ 'prof_base:prof_cand': mockImprovementData }}
        profileIds={['prof_base', 'prof_cand']}
        getProfileLabel={getProfileLabel}
      />,
    );

    expect(screen.getByTestId('paired-significance-panel')).toBeInTheDocument();
    expect(screen.getByText('verdict.significantImprovement')).toBeInTheDocument();
    expect(screen.getByText(/p = 0.0143/)).toBeInTheDocument();
    expect(screen.getByText(/\[\+3.5%, \+26.5%\]/)).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument(); // both pass
    expect(screen.getByText('+8')).toBeInTheDocument(); // cand only
    expect(screen.getByText('-2')).toBeInTheDocument(); // base only
    expect(screen.getByText('Safe to proceed with adoption.')).toBeInTheDocument();
    expect(screen.getByText('suggestedActionMap.proceed_with_gate')).toBeInTheDocument();
  });

  it('triggers onFilterCases when clicking regression cases filter button', () => {
    const onFilterCases = vi.fn();

    render(
      <PairedSignificancePanel
        pairedSignificance={{ 'prof_base:prof_cand': mockImprovementData }}
        profileIds={['prof_base', 'prof_cand']}
        getProfileLabel={getProfileLabel}
        onFilterCases={onFilterCases}
      />,
    );

    const regBtn = screen.getByText(/filterRegressionCases/);
    fireEvent.click(regBtn);

    expect(onFilterCases).toHaveBeenCalledWith([4, 18], 'regression');
  });

  it('triggers onFilterCases when clicking improved cases filter button', () => {
    const onFilterCases = vi.fn();

    render(
      <PairedSignificancePanel
        pairedSignificance={{ 'prof_base:prof_cand': mockImprovementData }}
        profileIds={['prof_base', 'prof_cand']}
        getProfileLabel={getProfileLabel}
        onFilterCases={onFilterCases}
      />,
    );

    const impBtn = screen.getByText(/filterImprovedCases/);
    fireEvent.click(impBtn);

    expect(onFilterCases).toHaveBeenCalledWith([1, 7, 12, 19, 23, 28, 33, 37], 'improved');
  });

  it('switches pairs when multiple paired results exist', () => {
    render(
      <PairedSignificancePanel
        pairedSignificance={{
          'prof_base:prof_cand': mockImprovementData,
          'prof_base:prof_cand2': mockRegressionData,
        }}
        profileIds={['prof_base', 'prof_cand', 'prof_cand2']}
        getProfileLabel={getProfileLabel}
      />,
    );

    expect(screen.getByText('verdict.significantImprovement')).toBeInTheDocument();

    const switchBtn = screen.getByText('Base-v1 ➔ Cand-v3');
    fireEvent.click(switchBtn);

    expect(screen.getByText('verdict.significantRegression')).toBeInTheDocument();
    expect(screen.getByText('Do not adopt this variant.')).toBeInTheDocument();
  });
});
