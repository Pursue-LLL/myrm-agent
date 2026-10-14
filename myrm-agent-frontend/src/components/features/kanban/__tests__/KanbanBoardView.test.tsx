/** @vitest-environment jsdom */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import { listTasks, moveTask, retryTask, type KanbanBoard, type KanbanTask, type TaskStatus } from '@/services/kanban';
import KanbanBoardView from '../KanbanBoardView';

vi.mock('next-intl', async () => {
  const actual = await vi.importActual<typeof import('next-intl')>('next-intl');
  const { default: messages } = await import('../../../../../locales/en.json');
  const translate = actual.createTranslator({ locale: 'en', messages, namespace: 'kanban' });
  return { useTranslations: () => translate, useLocale: () => 'en' };
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/kanban',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('next/dynamic', () => ({ default: () => () => null }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));
vi.mock('@/hooks/agent/useAgentName', () => ({
  useAgentNameMap: () => new Map<string, string>(),
  useAgentName: () => null,
}));

const agentState = { agents: [] as never[], fetchAgents: vi.fn() };
vi.mock('@/store/useAgentStore', () => ({
  default: (selector: (s: typeof agentState) => unknown) => selector(agentState),
  __esModule: true,
}));
const providerState = { getEnabledModels: () => [] };
vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (s: typeof providerState) => unknown) => selector(providerState),
  __esModule: true,
}));

vi.mock('@/services/kanban', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/kanban')>()),
  listTasks: vi.fn(),
  getBoardSummary: vi.fn().mockResolvedValue({
    board: {},
    task_counts: {},
    total_tasks: 0,
    dispatcher_active: false,
    by_agent: [],
    oldest_ready_age_seconds: null,
    stale_running_count: 0,
  }),
  listBoardEdges: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  moveTask: vi.fn(),
  retryTask: vi.fn(),
}));

const BOARD: KanbanBoard = {
  board_id: 'board-1',
  name: 'Ops',
  description: '',
  settings: {},
  created_at: '2026-08-10T00:00:00Z',
  updated_at: '2026-08-10T00:00:00Z',
} as KanbanBoard;

function makeTask(taskId: string, title: string, status: TaskStatus): KanbanTask {
  return {
    task_id: taskId,
    board_id: 'board-1',
    title,
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

const FAILED = makeTask('t-failed', 'Broken sync', 'failed');
const READY = makeTask('t-ready', 'Fresh draft', 'ready');

async function renderBoard() {
  vi.mocked(listTasks).mockResolvedValue({ items: [FAILED, READY], total: 2 });
  const user = userEvent.setup();
  render(<KanbanBoardView board={BOARD} onBack={vi.fn()} />);
  await screen.findByText('Broken sync');
  return user;
}

/** Opens the actions menu of the card with the given title: the nearest ancestor holding exactly one menu trigger. */
async function openCardMenu(user: ReturnType<typeof userEvent.setup>, title: string) {
  for (let el = screen.getByText(title).parentElement; el; el = el.parentElement) {
    const triggers = within(el).queryAllByRole('button', { name: 'Task actions' });
    if (triggers.length === 1) {
      await user.click(triggers[0]);
      return;
    }
    if (triggers.length > 1) {
      break;
    }
  }
  throw new Error(`No card menu found for ${title}`);
}

describe('KanbanBoardView retry, archive and move errors', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('retrying a failed card asks first, then calls the retry API and refreshes the board', async () => {
    vi.mocked(retryTask).mockResolvedValue({ ...FAILED, status: 'ready' });
    const user = await renderBoard();
    const callsBefore = vi.mocked(listTasks).mock.calls.length;

    await openCardMenu(user, 'Broken sync');
    await user.click(screen.getByRole('menuitem', { name: 'Retry' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Retry this task?');
    expect(retryTask).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('confirm-dialog-confirm'));

    await waitFor(() => expect(retryTask).toHaveBeenCalledWith('t-failed'));
    expect(moveTask).not.toHaveBeenCalled();
    await waitFor(() => expect(vi.mocked(listTasks).mock.calls.length).toBeGreaterThan(callsBefore));
    expect(toast.success).toHaveBeenCalledWith('Task queued to run again');
  });

  it('a failed retry shows the localized error, not the server message', async () => {
    vi.mocked(retryTask).mockRejectedValue(new ApiError('internal: sqlite busy at 0x7f'));
    const user = await renderBoard();

    await openCardMenu(user, 'Broken sync');
    await user.click(screen.getByRole('menuitem', { name: 'Retry' }));
    await user.click(await screen.findByTestId('confirm-dialog-confirm'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Failed to retry task'));
    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it('archiving from the card menu asks first and only then moves the task', async () => {
    vi.mocked(moveTask).mockResolvedValue({ ...FAILED, status: 'archived' });
    const user = await renderBoard();

    await openCardMenu(user, 'Broken sync');
    await user.click(screen.getByRole('menuitem', { name: 'Archive' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Archive this task?');
    expect(dialog).toHaveTextContent('"Broken sync"');
    expect(moveTask).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('confirm-dialog-confirm'));

    await waitFor(() => expect(moveTask).toHaveBeenCalledWith('t-failed', 'archived', { force: false }));
  });

  it('a rejected move shows the localized message, never the raw server text', async () => {
    vi.mocked(moveTask).mockRejectedValue(new ApiError('Cannot transition from ready to running: trace 9f3a'));
    const user = await renderBoard();

    await openCardMenu(user, 'Fresh draft');
    await user.click(screen.getByRole('menuitem', { name: 'Start' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Failed to move task'));
    expect(toast.error).toHaveBeenCalledTimes(1);
  });
});
