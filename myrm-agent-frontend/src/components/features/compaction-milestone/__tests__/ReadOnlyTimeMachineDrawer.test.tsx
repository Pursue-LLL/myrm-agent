/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ReadOnlyTimeMachineDrawer } from '../ReadOnlyTimeMachineDrawer';
import type { CompactedMessageSnapshot } from '../compactionTypes';

const stableT = (key: string, values?: Record<string, unknown>) => {
    if (values && 'count' in values) {
      return `${key}:${String(values.count)}`;
    }
    return key;
  };

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockMessages: CompactedMessageSnapshot[] = [
  {
    id: 'm1',
    role: 'user',
    content: 'Initial user query about architecture',
    timestamp: '10:00:00',
  },
  {
    id: 'm2',
    role: 'assistant',
    content: 'Agent detailed analysis and plan',
    timestamp: '10:01:00',
  },
  {
    id: 'm3',
    role: 'tool',
    content: 'Execution result: 200 OK',
    toolName: 'code-exec',
    timestamp: '10:02:00',
  },
];

describe('ReadOnlyTimeMachineDrawer component', () => {
  it('renders empty message fallback when message list is empty', () => {
    render(<ReadOnlyTimeMachineDrawer messages={[]} onClose={vi.fn()} />);

    expect(screen.getByText('emptyMessages')).toBeDefined();
    expect(screen.getByText('watermarkBadge')).toBeDefined();
  });

  it('renders raw archived messages with role indicators and timestamps', () => {
    render(<ReadOnlyTimeMachineDrawer messages={mockMessages} onClose={vi.fn()} />);

    expect(screen.getByText('openButton:3')).toBeDefined();
    expect(screen.getByText('watermarkBadge')).toBeDefined();

    expect(screen.getByText('Initial user query about architecture')).toBeDefined();
    expect(screen.getByText('Agent detailed analysis and plan')).toBeDefined();
    expect(screen.getByText('Execution result: 200 OK')).toBeDefined();
    expect(screen.getByText('code-exec')).toBeDefined();
  });

  it('calls onClose when close button is clicked', () => {
    const handleClose = vi.fn();
    render(<ReadOnlyTimeMachineDrawer messages={mockMessages} onClose={handleClose} />);

    const closeBtn = screen.getByRole('button', { name: /closeButton/i });
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
