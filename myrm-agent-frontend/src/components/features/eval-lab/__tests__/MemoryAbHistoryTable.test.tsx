import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import MemoryAbHistoryTable, { type MemoryAbHistoryItem } from '../MemoryAbHistoryTable';

function items(): MemoryAbHistoryItem[] {
  return [
    {
      timestamp: 2000,
      dataset_id: 'wb-bench-code',
      per_profile: {
        memory_off: { pass_rate: 0.5, pass_count: 5, fail_count: 5, error_count: 0, memory_tool_calls: 0 },
        memory_on: { pass_rate: 0.8, pass_count: 8, fail_count: 2, error_count: 0, memory_tool_calls: 3 },
      },
    },
    {
      timestamp: 1000,
      dataset_id: 'wb-bench-research',
      per_profile: {
        memory_off: { pass_rate: 0.6 },
        memory_on: { pass_rate: 0.9 },
      },
    },
  ];
}

describe('MemoryAbHistoryTable', () => {
  it('renders nothing when there is no history', () => {
    const { container } = render(<MemoryAbHistoryTable items={[]} onSelect={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders dataset, arm pass rates and memory call counts', () => {
    render(<MemoryAbHistoryTable items={items()} onSelect={vi.fn()} />);

    expect(screen.getByText('historyTitle')).toBeInTheDocument();
    expect(screen.getByText('code')).toBeInTheDocument();
    expect(screen.getByText('research')).toBeInTheDocument();

    // off arm 50% with 0 memory calls, on arm 80% with 3 calls
    const firstRow = screen.getByText('code').closest('tr');
    expect(firstRow).not.toBeNull();
    expect(firstRow!.textContent).toContain('50%');
    expect(firstRow!.textContent).toContain('(0)');
    expect(firstRow!.textContent).toContain('80%');
    expect(firstRow!.textContent).toContain('(3)');
  });

  it('falls back to dash for arms without per-profile data', () => {
    render(<MemoryAbHistoryTable items={items()} onSelect={vi.fn()} />);

    const secondRow = screen.getByText('research').closest('tr');
    expect(secondRow).not.toBeNull();
    expect(secondRow!.textContent).toContain('60%');
    expect(secondRow!.textContent).toContain('90%');
    expect(secondRow!.textContent).not.toContain('(0)');
  });

  it('marks the selected run as current and calls onSelect for others', async () => {
    const onSelect = vi.fn();
    render(<MemoryAbHistoryTable items={items()} selectedTimestamp={2000} onSelect={onSelect} />);

    const selectedRow = screen.getByText('code').closest('tr');
    expect(selectedRow!.textContent).toContain('historyCurrent');

    await userEvent.click(screen.getByText('historyView'));
    expect(onSelect).toHaveBeenCalledWith(1000);
  });
});
