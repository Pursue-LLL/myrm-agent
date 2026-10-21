import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { KanbanEventTimeline } from '../KanbanEventTimeline';
import type { TaskEvent } from '@/services/kanban';

const tMock = vi.fn((key: string) => key);

vi.mock('next-intl', () => ({
  useTranslations: () => tMock,
}));

vi.mock('../KanbanMarkdown', () => ({
  default: ({ children }: { children: string }) => <div data-testid="kanban-markdown">{children}</div>,
}));

function event(overrides: Partial<TaskEvent>): TaskEvent {
  return {
    event_id: 1,
    task_id: 't1',
    kind: 'approved',
    payload: {},
    created_at: '2026-08-09T00:00:00Z',
    ...overrides,
  };
}

describe('KanbanEventTimeline approval details', () => {
  beforeEach(() => {
    tMock.mockClear();
  });

  it('renders approver for approved events', () => {
    render(<KanbanEventTimeline events={[event({ kind: 'approved', payload: { approver: 'alice' } })]} />);
    expect(tMock).toHaveBeenCalledWith('approvedBy', { approver: 'alice' });
  });

  it('falls back to "human" when approved payload has no approver', () => {
    render(<KanbanEventTimeline events={[event({ kind: 'approved', payload: {} })]} />);
    expect(tMock).toHaveBeenCalledWith('approvedBy', { approver: 'human' });
  });

  it('renders approver and markdown reason for rejected events', () => {
    render(
      <KanbanEventTimeline
        events={[
          event({
            kind: 'rejected',
            payload: { approver: 'bob', reason: 'needs citations' },
          }),
        ]}
      />,
    );
    expect(tMock).toHaveBeenCalledWith('rejectedBy', { approver: 'bob' });
    expect(screen.getByTestId('kanban-markdown')).toHaveTextContent('needs citations');
  });

  it('omits reason block when rejected payload has no reason', () => {
    render(<KanbanEventTimeline events={[event({ kind: 'rejected', payload: { approver: 'bob' } })]} />);
    expect(tMock).toHaveBeenCalledWith('rejectedBy', { approver: 'bob' });
    expect(screen.queryByTestId('kanban-markdown')).toBeNull();
  });
});
