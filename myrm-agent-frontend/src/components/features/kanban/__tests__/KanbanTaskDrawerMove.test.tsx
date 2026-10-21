/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { moveTask } from '@/services/kanban';
import KanbanTaskDrawer from '../KanbanTaskDrawer';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/hooks/agent/useAgentName', () => ({
  useAgentName: () => null,
}));

const mockAgentStore = { agents: [] as never[], fetchAgents: vi.fn() };
vi.mock('@/store/useAgentStore', () => ({
  default: (selector: (s: typeof mockAgentStore) => unknown) => selector(mockAgentStore),
  __esModule: true,
}));

vi.mock('@/services/kanban', () => ({
  listRuns: vi.fn().mockResolvedValue({ items: [] }),
  listEvents: vi.fn().mockResolvedValue({ items: [] }),
  listDependencies: vi.fn().mockResolvedValue({ items: [] }),
  listDependents: vi.fn().mockResolvedValue({ items: [] }),
  moveTask: vi.fn().mockResolvedValue({}),
  promoteTask: vi.fn(),
  reclaimTask: vi.fn(),
  updateTask: vi.fn().mockResolvedValue({}),
  getTaskDiagnostics: vi.fn().mockResolvedValue({ diagnostics: [] }),
  raceLanes: vi.fn().mockResolvedValue({ parent_task_id: '', lanes: [] }),
  KANBAN_SOURCE_CHAT_METADATA_KEY: 'source_chat_id',
}));

vi.mock('@/lib/api', () => ({
  getApiUrl: (path: string) => `http://localhost:8080/api/v1${path}`,
}));

vi.mock('../KanbanDiagnosticsSection', () => ({ default: () => null }));
vi.mock('../KanbanTaskHandoffSection', () => ({ KanbanTaskHandoffSection: () => null }));
vi.mock('../RaceSection', () => ({ default: () => null }));
vi.mock('../KanbanTaskExecutionTraceSection', () => ({ default: () => null }));
vi.mock('../KanbanEventTimeline', () => ({
  KanbanRunHistory: () => null,
  KanbanEventTimeline: () => null,
}));
vi.mock('../KanbanMarkdown', () => ({
  default: ({ children }: { children: string }) => <span>{children}</span>,
}));

function makeTask(status: TaskStatus): KanbanTask {
  return {
    task_id: 'task-1',
    board_id: 'board-1',
    title: 'Weekly report',
    description: '',
    status,
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
  };
}

async function renderDrawer(status: TaskStatus) {
  const onOpenChange = vi.fn();
  const onRefresh = vi.fn();
  const onRequestMove = vi.fn();
  const task = makeTask(status);
  render(
    <KanbanTaskDrawer
      task={task}
      allTasks={[task]}
      open={true}
      onOpenChange={onOpenChange}
      onRefresh={onRefresh}
      onRequestMove={onRequestMove}
      enabledModels={[]}
    />,
  );
  await screen.findByTestId('kanban-task-drawer');
  return { onOpenChange, onRefresh, onRequestMove };
}

describe('KanbanTaskDrawer status actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  it('a failed task shows Retry instead of a move to Ready', async () => {
    await renderDrawer('failed');

    expect(screen.getByRole('button', { name: 'retryAction' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'moveTo.ready' })).toBeNull();
  });

  it('Retry hands the move to the board confirmation instead of calling the move API', async () => {
    const user = userEvent.setup();
    const { onRequestMove, onOpenChange } = await renderDrawer('failed');

    await user.click(screen.getByRole('button', { name: 'retryAction' }));

    expect(onRequestMove).toHaveBeenCalledWith('task-1', 'ready');
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(moveTask).not.toHaveBeenCalled();
  });

  it('Archive also goes through the board confirmation', async () => {
    const user = userEvent.setup();
    const { onRequestMove, onOpenChange } = await renderDrawer('completed');

    await user.click(screen.getByRole('button', { name: 'moveTo.archived' }));

    expect(onRequestMove).toHaveBeenCalledWith('task-1', 'archived');
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(moveTask).not.toHaveBeenCalled();
  });

  it('an ordinary move is still done by the drawer itself', async () => {
    const user = userEvent.setup();
    const { onRequestMove, onRefresh } = await renderDrawer('ready');

    await user.click(screen.getByRole('button', { name: 'moveTo.running' }));

    await waitFor(() => expect(moveTask).toHaveBeenCalledWith('task-1', 'running'));
    expect(onRefresh).toHaveBeenCalled();
    expect(onRequestMove).not.toHaveBeenCalled();
  });
});
