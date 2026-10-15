import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import KanbanTaskCard from '../KanbanTaskCard';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/agent/useAgentName', () => ({
  useAgentName: () => null,
}));

vi.mock('../KanbanSpecifyDialog', () => ({
  default: () => null,
}));

vi.mock('../KanbanDecomposeDialog', () => ({
  default: () => null,
}));

vi.mock('../KanbanMarkdown', () => ({
  default: ({ children }: { children: string }) => <span>{children}</span>,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/services/kanban', () => ({
  hasKanbanCompletionIntent: () => false,
  listRuns: vi.fn().mockResolvedValue({ items: [] }),
  listEvents: vi.fn().mockResolvedValue({ items: [] }),
  listDependencies: vi.fn().mockResolvedValue({ items: [] }),
  listDependents: vi.fn().mockResolvedValue({ items: [] }),
  getTask: vi.fn(),
  addComment: vi.fn(),
  addDependency: vi.fn(),
  removeDependency: vi.fn(),
}));

vi.mock('lucide-react', () => ({
  Clock: () => <span />,
  ExternalLink: () => <span />,
  GitBranch: () => <span />,
  Paperclip: () => <span />,
  User: () => <span />,
  ShieldAlert: () => <span />,
  ShieldCheck: () => <span />,
  UserCheck: () => <span />,
  Bot: () => <span />,
}));

function makeTask(overrides: Partial<KanbanTask> = {}): KanbanTask {
  return {
    task_id: 'task-queued-1',
    board_id: 'board-1',
    title: 'Queued Task',
    description: '',
    status: 'ready' as TaskStatus,
    priority: 'normal',
    retry_count: 0,
    max_retries: 3,
    consecutive_failures: 0,
    result: '',
    error: '',
    metadata: {},
    extra_skill_ids: [],
    attachment_ids: [],
    attachments: [],
    dep_count: 0,
    children_total: 0,
    children_done: 0,
    comment_count: 0,
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:00:00Z',
    ...overrides,
  };
}

const noop = () => {};

describe('KanbanTaskCard concurrency queued badge', () => {
  it('renders queued badge for a ready task when concurrency is full', () => {
    render(
      <KanbanTaskCard
        task={makeTask({ status: 'ready' })}
        allTasks={[]}
        onMove={noop}
        onDelete={noop}
        onRefresh={noop}
        queuedByConcurrency
      />,
    );
    expect(screen.getByTestId('kanban-task-queued-badge')).toBeTruthy();
  });

  it('does not render the badge when concurrency is not full', () => {
    render(
      <KanbanTaskCard
        task={makeTask({ status: 'ready' })}
        allTasks={[]}
        onMove={noop}
        onDelete={noop}
        onRefresh={noop}
      />,
    );
    expect(screen.queryByTestId('kanban-task-queued-badge')).toBeNull();
  });

  it('does not render the badge for a running task even when concurrency is full', () => {
    render(
      <KanbanTaskCard
        task={makeTask({ status: 'running' })}
        allTasks={[]}
        onMove={noop}
        onDelete={noop}
        onRefresh={noop}
        queuedByConcurrency
      />,
    );
    expect(screen.queryByTestId('kanban-task-queued-badge')).toBeNull();
  });
});

describe('KanbanTaskCard details toggle', () => {
  it('names the toggle once and reports its state through aria-expanded', async () => {
    render(<KanbanTaskCard task={makeTask()} allTasks={[]} onMove={noop} onDelete={noop} onRefresh={noop} />);

    const toggle = screen.getByRole('button', { name: 'taskDetails', expanded: false });
    fireEvent.click(toggle);

    await waitFor(() => expect(screen.getByRole('button', { name: 'taskDetails', expanded: true })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: 'taskDetails', expanded: true }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'taskDetails', expanded: false })).toBeTruthy());
  });
});
