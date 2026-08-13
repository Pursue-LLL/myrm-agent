import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import MatrixResultView, { type MatrixReportData } from '../components/MatrixResultView';

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

describe('MatrixResultView trajectory disclosure columns', () => {
  it('shows tool calls and limit hits columns when any profile reports total_tool_calls', () => {
    const report = baseReport();
    report.per_profile.memory_on.total_tool_calls = 8;
    report.per_profile.memory_on.limit_hits = 2;
    report.per_profile.memory_on.blocked_count = 1;

    render(
      <MatrixResultView
        report={report}
        profileNames={{ memory_off: 'No Memory', memory_on: 'With Memory' }}
      />,
    );

    expect(screen.getByText('evalLab.matrix.toolCalls')).toBeInTheDocument();
    expect(screen.getByText('evalLab.matrix.limitHits')).toBeInTheDocument();
    const memoryOnRow = screen.getAllByText('With Memory')[0].closest('tr');
    expect(memoryOnRow).not.toBeNull();
    expect(memoryOnRow!.textContent).toContain('8');
    expect(memoryOnRow!.textContent).toContain('2');
  });

  it('shows blocked badge in the matrix grid when a cell reports blocks', () => {
    const report = baseReport();
    report.per_profile.memory_on.total_tool_calls = 5;
    report.matrix = [
      {
        case_index: 0,
        message: 'fetch a remote artifact',
        profiles: {
          memory_off: { passed: true, total_ms: 500, token_usage: {}, cost: 0, error: null },
          memory_on: {
            passed: false,
            total_ms: 900,
            token_usage: {},
            cost: 0,
            error: 'blocked',
            tool_calls: 5,
            limit_reached: 'max_tool_calls',
            blocked_count: 2,
          },
        },
      },
    ];

    render(<MatrixResultView report={report} />);

    // The header column and the cell badge both say `limitHits`.
    expect(screen.getAllByText('evalLab.matrix.limitHits').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/evalLab\.matrix\.blocked 2/)).toBeInTheDocument();
    expect(screen.getByText('5×')).toBeInTheDocument();
  });

  it('hides the columns for plain reports without trajectory fields', () => {
    render(<MatrixResultView report={baseReport()} />);

    expect(screen.queryByText('evalLab.matrix.toolCalls')).not.toBeInTheDocument();
    expect(screen.queryByText('evalLab.matrix.limitHits')).not.toBeInTheDocument();
  });
});

describe('MatrixResultView sampled disclosure', () => {
  it('shows the sampled badge when the report ran on a sample', () => {
    const report = baseReport();
    report.limit = 20;

    render(<MatrixResultView report={report} />);

    expect(screen.getByText(/evalLab\.matrix\.sampled · 20/)).toBeInTheDocument();
  });

  it('omits the badge for full runs', () => {
    render(<MatrixResultView report={baseReport()} />);

    expect(screen.queryByText(/evalLab\.matrix\.sampled/)).not.toBeInTheDocument();
  });
});

describe('MatrixResultView shared disclosure area', () => {
  it('shows harness_version for every report type', () => {
    const report = baseReport();
    report.harness_version = '0.18.0';

    render(<MatrixResultView report={report} />);

    expect(screen.getByText(/evalLab\.layers\.harnessVersion/)).toHaveTextContent(
      'evalLab.layers.harnessVersion: 0.18.0',
    );
  });

  it('shows the based-on profile for layered reports', () => {
    const report = baseReport();
    report.eval_type = 'layered';
    report.profile_id = 'hermes_assistant';

    render(
      <MatrixResultView
        report={report}
        profileNames={{ hermes_assistant: 'Hermes Assistant' }}
      />,
    );

    expect(screen.getByText(/evalLab\.layers\.basedOnProfile/)).toHaveTextContent(
      'evalLab.layers.basedOnProfile: Hermes Assistant',
    );
  });

  it('hides the disclosure area for plain matrix reports without the fields', () => {
    render(<MatrixResultView report={baseReport()} />);

    expect(screen.queryByText(/harnessVersion/)).not.toBeInTheDocument();
    expect(screen.queryByText(/basedOnProfile/)).not.toBeInTheDocument();
  });
});

describe('MatrixResultView run budget disclosure', () => {
  it('shows the budget badge when the report discloses run caps', () => {
    const report = baseReport();
    report.max_tool_calls = 100;
    report.max_iterations = 150;

    render(<MatrixResultView report={report} />);

    expect(screen.getByText(/100 evalLab\.matrix\.budgetToolCalls/)).toBeInTheDocument();
    expect(screen.getByText(/150 evalLab\.matrix\.budgetIterations/)).toBeInTheDocument();
    expect(screen.getByText('evalLab.matrix.budgetHint')).toBeInTheDocument();
  });

  it('omits the budget badge for reports without caps', () => {
    render(<MatrixResultView report={baseReport()} />);

    expect(screen.queryByText(/evalLab\.matrix\.budget/)).not.toBeInTheDocument();
  });
});

describe('MatrixResultView decontamination disclosure', () => {
  it('shows the enabled badge when decontamination was active', () => {
    const report = baseReport();
    report.harness_version = '0.18.0';
    report.decontam_active = true;

    render(<MatrixResultView report={report} />);

    expect(screen.getByText('evalLab.layers.decontamOn')).toBeInTheDocument();
  });

  it('shows the disabled badge when decontamination was off', () => {
    const report = baseReport();
    report.harness_version = '0.18.0';
    report.decontam_active = false;

    render(<MatrixResultView report={report} />);

    expect(screen.getByText('evalLab.layers.decontamOff')).toBeInTheDocument();
  });

  it('omits the badge when the report has no decontamination field', () => {
    render(<MatrixResultView report={baseReport()} />);

    expect(screen.queryByText(/decontam/)).not.toBeInTheDocument();
  });
});
