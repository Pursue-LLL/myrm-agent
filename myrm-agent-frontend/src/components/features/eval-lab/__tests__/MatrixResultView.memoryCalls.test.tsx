import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import MatrixResultView, { type MatrixReportData } from '../MatrixResultView';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

function baseReport(): MatrixReportData {
  return {
    profile_ids: ['memory_off', 'memory_on'],
    total_cases: 1,
    stable_count: 1,
    regression_count: 0,
    stable_rate: 1,
    per_profile: {
      memory_off: {
        pass_count: 1,
        fail_count: 0,
        error_count: 0,
        pass_rate: 1,
        total_tokens: 100,
        total_cost: 0.001,
        total_ms: 1000,
      },
      memory_on: {
        pass_count: 1,
        fail_count: 0,
        error_count: 0,
        pass_rate: 1,
        total_tokens: 100,
        total_cost: 0.001,
        total_ms: 1000,
      },
    },
    matrix: [],
    total_ms: 1000,
  };
}

describe('MatrixResultView memory engagement column', () => {
  it('shows the memory calls column when any arm reports memory_tool_calls', () => {
    const report = baseReport();
    report.per_profile.memory_off.memory_tool_calls = 0;
    report.per_profile.memory_on.memory_tool_calls = 3;

    render(<MatrixResultView report={report} profileNames={{ memory_off: 'No Memory', memory_on: 'With Memory' }} />);

    expect(screen.getByText('evalLab.matrix.memoryCalls')).toBeInTheDocument();
    const memoryOnRow = screen.getAllByText('With Memory')[0].closest('tr');
    expect(memoryOnRow).not.toBeNull();
    expect(memoryOnRow!.textContent).toContain('3');
    const memoryOffRow = screen.getAllByText('No Memory')[0].closest('tr');
    expect(memoryOffRow).not.toBeNull();
    expect(memoryOffRow!.textContent).toContain('0');
  });

  it('hides the column for plain matrix reports without the field', () => {
    render(<MatrixResultView report={baseReport()} />);

    expect(screen.queryByText('evalLab.matrix.memoryCalls')).not.toBeInTheDocument();
  });
});

describe('MatrixResultView aborted report notice', () => {
  it('shows the aborted notice when the report is flagged incomplete', () => {
    const report = baseReport();
    report.aborted = true;

    render(<MatrixResultView report={report} />);

    expect(screen.getByText('evalLab.layers.abortedNotice')).toBeInTheDocument();
  });

  it('omits the notice for complete reports', () => {
    render(<MatrixResultView report={baseReport()} />);

    expect(screen.queryByText('evalLab.layers.abortedNotice')).not.toBeInTheDocument();
  });
});
