/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import {
  bulkAction,
  listTasks,
  moveTask,
  retryTask,
  type BulkActionResult,
  type KanbanBoard,
  type KanbanTask,
  type TaskStatus,
} from '@/services/kanban';
import KanbanBoardView from '../KanbanBoardView';

vi.mock('next-intl', async () => {
  const actual = await vi.importActual<typeof import('next-intl')>('next-intl');
  const { default: messages } = await import('../../../../../locales/en.json');
  // The board reads `kanban`, and its drag-and-drop hook reads `common.dnd`; each namespace keeps one stable
  // translator so memoized consumers do not rebuild on every render.
  const board = actual.createTranslator({ locale: 'en', messages, namespace: 'kanban' });
  const dnd = actual.createTranslator({ locale: 'en', messages, namespace: 'common.dnd' });
  return { useTranslations: (namespace?: string) => (namespace === 'common.dnd' ? dnd : board), useLocale: () => 'en' };
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
  bulkAction: vi.fn(),
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

describe('KanbanBoardView bulk selection', () => {
  // The API order interleaves columns, as it does in production.
  const ALPHA = makeTask('t-alpha', 'Alpha ready', 'ready');
  const BRAVO = makeTask('t-bravo', 'Bravo backlog', 'backlog');
  const DELTA = makeTask('t-delta', 'Delta ready', 'ready');

  const bulkResult = (failedIds: string[]): BulkActionResult => ({
    results: ['t-alpha', 't-bravo'].map((taskId) => ({ task_id: taskId, success: !failedIds.includes(taskId) })),
    total: 2,
    succeeded: 2 - failedIds.length,
    failed: failedIds.length,
  });

  const ctrlClick = (title: string) => fireEvent.click(screen.getByText(title), { metaKey: true });
  const bar = () => screen.queryByTestId('kanban-bulk-bar');

  async function renderSelectable() {
    vi.mocked(listTasks).mockResolvedValue({ items: [ALPHA, BRAVO, DELTA], total: 3 });
    const user = userEvent.setup();
    render(<KanbanBoardView board={BOARD} onBack={vi.fn()} />);
    await screen.findByText('Alpha ready');
    return user;
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('Shift-click selects the cards between the clicks in that column, not the other columns in between', async () => {
    await renderSelectable();

    ctrlClick('Alpha ready');
    fireEvent.click(screen.getByText('Delta ready'), { shiftKey: true });

    expect(bar()).toHaveTextContent('2 selected');
  });

  it('after a partial failure only the failed task stays selected', async () => {
    vi.mocked(bulkAction).mockResolvedValue(bulkResult(['t-bravo']));
    const user = await renderSelectable();
    ctrlClick('Alpha ready');
    ctrlClick('Bravo backlog');
    expect(bar()).toHaveTextContent('2 selected');

    await user.click(screen.getByRole('button', { name: 'Archive' }));
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(bar()).toHaveTextContent('1 selected'));
    expect(bulkAction).toHaveBeenCalledWith('board-1', ['t-alpha', 't-bravo'], 'archive', {}, false);
  });

  it('after a fully successful action the selection is empty', async () => {
    vi.mocked(bulkAction).mockResolvedValue(bulkResult([]));
    const user = await renderSelectable();
    ctrlClick('Alpha ready');
    ctrlClick('Bravo backlog');

    await user.click(screen.getByRole('button', { name: 'Archive' }));
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(bar()).toBeNull());
  });

  it('Escape closes an open bar menu first and only a second Escape clears the selection', async () => {
    const user = await renderSelectable();
    ctrlClick('Alpha ready');
    ctrlClick('Bravo backlog');
    await user.click(screen.getByRole('button', { name: 'Move to' }));
    expect(await screen.findByRole('menuitem', { name: 'Ready' })).toBeTruthy();

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
    expect(bar()).toHaveTextContent('2 selected');

    await user.keyboard('{Escape}');
    await waitFor(() => expect(bar()).toBeNull());
  });

  it('a selected task that disappears after a refresh leaves the selection', async () => {
    await renderSelectable();
    ctrlClick('Alpha ready');
    ctrlClick('Bravo backlog');
    expect(bar()).toHaveTextContent('2 selected');

    vi.mocked(listTasks).mockResolvedValue({ items: [ALPHA, DELTA], total: 2 });
    window.dispatchEvent(new CustomEvent('kanban-task-updated', { detail: { board_id: 'board-1' } }));

    await waitFor(() => expect(bar()).toHaveTextContent('1 selected'));
  });

  it('a selected task that the responsibility filter hides leaves the selection', async () => {
    const charlie = makeTask('t-charlie', 'Charlie broken', 'failed');
    vi.mocked(listTasks).mockResolvedValue({ items: [ALPHA, charlie], total: 2 });
    const user = userEvent.setup();
    render(<KanbanBoardView board={BOARD} onBack={vi.fn()} />);
    await screen.findByText('Alpha ready');
    ctrlClick('Alpha ready');
    ctrlClick('Charlie broken');
    expect(bar()).toHaveTextContent('2 selected');

    await user.click(screen.getByRole('button', { name: 'Needs Action' }));

    await waitFor(() => expect(bar()).toHaveTextContent('1 selected'));
    expect(screen.queryByText('Alpha ready')).toBeNull();
  });
});
