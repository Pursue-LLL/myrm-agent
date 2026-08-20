import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import MatrixHistoryTable, { type MatrixHistoryItem } from '../components/MatrixHistoryTable';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

function item(partial: Partial<MatrixHistoryItem>): MatrixHistoryItem {
  return {
    timestamp: 1700000000,
    dataset_id: 'wb-bench-math',
    agent_model: 'claude-3',
    judge_model: 'judge-1',
    stable_rate: 0.8,
    ...partial,
  };
}

describe('MatrixHistoryTable', () => {
  it('renders nothing when there is no history', () => {
    const { container } = render(<MatrixHistoryTable items={[]} onSelect={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders a row per report with formatted values', () => {
    render(
      <MatrixHistoryTable
        items={[
          item({ timestamp: 1700000000, dataset_id: 'wb-bench-math' }),
          item({ timestamp: 1700000100, dataset_id: 'wb-bench-coding', stable_rate: 0.5 }),
        ]}
        onSelect={() => {}}
      />,
    );

    expect(screen.getByText('math')).toBeInTheDocument();
    expect(screen.getByText('coding')).toBeInTheDocument();
    expect(screen.getByText('80%')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getAllByText('claude-3')).toHaveLength(2);
    expect(screen.getAllByText('judge-1')).toHaveLength(2);
  });

  it('marks layered reports with a badge and shows sample / aborted badges', () => {
    render(
      <MatrixHistoryTable
        items={[
          item({
            eval_type: 'layered',
            limit: 10,
            aborted: true,
            stable_rate: null,
            agent_model: 'unknown',
            judge_model: 'none',
          }),
        ]}
        onSelect={() => {}}
      />,
    );

    expect(screen.getByText('evalLab.matrix.historyLayeredBadge')).toBeInTheDocument();
    expect(screen.getByText(/evalLab\.matrix\.sampled · 10/)).toBeInTheDocument();
    expect(screen.getByText('evalLab.matrix.historyAbortedBadge')).toBeInTheDocument();
    expect(screen.getAllByText('-').length).toBeGreaterThanOrEqual(2);
  });

  it('calls onSelect with the timestamp when view is clicked', () => {
    const onSelect = vi.fn();
    render(<MatrixHistoryTable items={[item({ timestamp: 42 }), item({ timestamp: 43 })]} onSelect={onSelect} />);

    const buttons = screen.getAllByRole('button');
    buttons[0].click();
    expect(onSelect).toHaveBeenCalledWith(42);
  });

  it('shows a disabled current marker for the selected report', () => {
    render(
      <MatrixHistoryTable
        items={[item({ timestamp: 42 }), item({ timestamp: 43 })]}
        selectedTimestamp={42}
        onSelect={() => {}}
      />,
    );

    const buttons = screen.getAllByRole('button');
    expect(buttons[0]).toBeDisabled();
    expect(buttons[0]).toHaveTextContent('evalLab.matrix.historyCurrent');
    expect(buttons[1]).toHaveTextContent('evalLab.matrix.historyView');
  });
});
