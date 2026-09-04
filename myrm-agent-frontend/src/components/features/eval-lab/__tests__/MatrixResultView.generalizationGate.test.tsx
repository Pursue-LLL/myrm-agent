// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import MatrixResultView, { type MatrixReportData } from '../components/MatrixResultView';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

function baseReport(): MatrixReportData {
  return {
    profile_ids: ['qwen_7b', 'claude_35'],
    total_cases: 4,
    stable_count: 3,
    regression_count: 1,
    stable_rate: 0.75,
    per_profile: {
      qwen_7b: {
        pass_count: 4,
        fail_count: 0,
        error_count: 0,
        pass_rate: 1.0,
        total_tokens: 1000,
        total_cost: 0.01,
        total_ms: 2000,
      },
      claude_35: {
        pass_count: 3,
        fail_count: 1,
        error_count: 0,
        pass_rate: 0.75,
        total_tokens: 1200,
        total_cost: 0.05,
        total_ms: 1800,
      },
    },
    matrix: [],
    total_ms: 3800,
  };
}

describe('MatrixResultView Generalization Gate banner', () => {
  it('does not render banner when generalization_gate is undefined', () => {
    const report = baseReport();
    render(<MatrixResultView report={report} />);
    expect(screen.queryByTestId('generalization-gate-banner')).toBeNull();
  });

  it('renders passed gate with green badge and metrics', () => {
    const report = baseReport();
    report.generalization_gate = {
      verdict: 'passed',
      min_required_profiles: 2,
      evaluated_profile_count: 2,
      passed_profile_count: 2,
      regression_case_count: 0,
      stable_case_count: 4,
      mean_pass_rate: 0.9,
      pass_rate_spread: 0.1,
      recommendation: 'Cross-model generalization verified. Safe to adopt globally.',
    };

    render(<MatrixResultView report={report} />);
    const banner = screen.getByTestId('generalization-gate-banner');
    expect(banner).toBeInTheDocument();
    expect(screen.getByTestId('gate-verdict-badge').textContent).toBe('evalLab.matrix.gate.passed');
    expect(screen.getByText('Cross-model generalization verified. Safe to adopt globally.')).toBeInTheDocument();
    expect(screen.getByText('2/2 (≥2)')).toBeInTheDocument();
    expect(screen.getByText('10.0%')).toBeInTheDocument();
  });

  it('renders partial overfit warning badge when verdict is partial_overfit', () => {
    const report = baseReport();
    report.generalization_gate = {
      verdict: 'partial_overfit',
      min_required_profiles: 2,
      evaluated_profile_count: 2,
      passed_profile_count: 1,
      regression_case_count: 2,
      stable_case_count: 2,
      mean_pass_rate: 0.6,
      pass_rate_spread: 0.5,
      recommendation: 'Overfitting detected. Patch likely addresses single-model pathology.',
    };

    render(<MatrixResultView report={report} />);
    expect(screen.getByTestId('gate-verdict-badge').textContent).toBe('evalLab.matrix.gate.partialOverfit');
    expect(screen.getByText('Overfitting detected. Patch likely addresses single-model pathology.')).toBeInTheDocument();
    expect(screen.getByText('1/2 (≥2)')).toBeInTheDocument();
  });
});
