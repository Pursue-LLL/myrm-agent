/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent, { PointerEventsCheckLevel } from '@testing-library/user-event';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { bulkAction, type TaskStatus } from '@/services/kanban';
import KanbanBulkActionBar from '../KanbanBulkActionBar';

vi.mock('next-intl', async () => {
  const actual = await vi.importActual<typeof import('next-intl')>('next-intl');
  const { default: messages } = await import('../../../../../locales/en.json');
  const translate = actual.createTranslator({ locale: 'en', messages, namespace: 'kanban' });
  return { useTranslations: () => translate };
});

vi.mock('sonner', () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));

vi.mock('@/services/kanban', () => ({
  bulkAction: vi.fn().mockResolvedValue({ succeeded: 2, failed: 0 }),
}));

function renderBar(selectedStatuses: TaskStatus[] = ['ready', 'blocked'], agents: { id: string; name: string }[] = []) {
  const onClear = vi.fn();
  const onComplete = vi.fn();
  render(
    <KanbanBulkActionBar
      boardId="board-1"
      selectedIds={['t1', 't2']}
      selectedStatuses={selectedStatuses}
      onClear={onClear}
      onComplete={onComplete}
      agents={agents}
    />,
  );
  return { onClear, onComplete };
}

describe('KanbanBulkActionBar archive and delete confirmation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('archiving asks first with the selected count and sends nothing yet', async () => {
    const user = userEvent.setup();
    renderBar();

    await user.click(screen.getByRole('button', { name: 'Archive' }));

    expect(screen.getByText('Archive 2 tasks?')).toBeTruthy();
    expect(bulkAction).not.toHaveBeenCalled();
  });

  it('confirming archives the whole selection without the delete-only confirm flag', async () => {
    const user = userEvent.setup();
    const { onClear, onComplete } = renderBar();

    await user.click(screen.getByRole('button', { name: 'Archive' }));
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(bulkAction).toHaveBeenCalledWith('board-1', ['t1', 't2'], 'archive', {}, false));
    expect(onClear).toHaveBeenCalled();
    expect(onComplete).toHaveBeenCalled();
  });

  it('cancelling puts the Archive button back and archives nothing', async () => {
    const user = userEvent.setup();
    renderBar();

    await user.click(screen.getByRole('button', { name: 'Archive' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByText('Archive 2 tasks?')).toBeNull();
    expect(screen.getByRole('button', { name: 'Archive' })).toBeTruthy();
    expect(bulkAction).not.toHaveBeenCalled();
  });

  it('only one confirmation is open at a time', async () => {
    const user = userEvent.setup();
    renderBar();

    await user.click(screen.getByRole('button', { name: 'Archive' }));
    await user.click(screen.getByRole('button', { name: 'Delete' }));

    expect(screen.queryByText('Archive 2 tasks?')).toBeNull();
    expect(screen.getByText('Delete 2 tasks?')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Archive' })).toBeTruthy();
  });

  it('delete still needs its confirmation and sends the confirm flag', async () => {
    const user = userEvent.setup();
    renderBar();

    await user.click(screen.getByRole('button', { name: 'Delete' }));
    expect(bulkAction).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(bulkAction).toHaveBeenCalledWith('board-1', ['t1', 't2'], 'delete', {}, true));
  });
});

describe('KanbanBulkActionBar when the request itself fails', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a localized message instead of the raw error and keeps the selection', async () => {
    vi.mocked(bulkAction).mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const user = userEvent.setup();
    const { onClear, onComplete } = renderBar();

    await user.click(screen.getByRole('button', { name: 'Archive' }));
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Failed to update task'));
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(onClear).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });
});

describe('KanbanBulkActionBar move targets follow the selection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function openMoveMenu(selectedStatuses: TaskStatus[]) {
    const user = userEvent.setup();
    renderBar(selectedStatuses);
    await user.click(screen.getByRole('button', { name: 'Move to' }));
    return user;
  }

  it('offers every target when the selection can move anywhere, and a click sends the move', async () => {
    const user = await openMoveMenu(['ready', 'blocked']);

    expect(screen.getByRole('menuitem', { name: 'Ready' })).toBeTruthy();
    expect(screen.getByRole('menuitem', { name: 'Blocked' })).toBeTruthy();
    expect(screen.getByRole('menuitem', { name: 'Completed' })).toBeTruthy();

    await user.click(screen.getByRole('menuitem', { name: 'Blocked' }));

    await waitFor(() =>
      expect(bulkAction).toHaveBeenCalledWith('board-1', ['t1', 't2'], 'move', { status: 'blocked' }, false),
    );
  });

  const UNMOVABLE_SELECTIONS: { label: string; statuses: TaskStatus[] }[] = [
    { label: 'failed and completed', statuses: ['failed', 'completed'] },
    { label: 'in review', statuses: ['in_review'] },
    { label: 'failed', statuses: ['failed'] },
  ];

  it.each(UNMOVABLE_SELECTIONS)('hides the Move action when no selected task can be moved ($label)', ({ statuses }) => {
    renderBar(statuses);

    expect(screen.queryByRole('button', { name: 'Move to' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Archive' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Reassign' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeTruthy();
  });

  it('keeps a target that at least one selected task can reach, so mixed moves still partly succeed', async () => {
    await openMoveMenu(['failed', 'triage']);

    expect(screen.getByRole('menuitem', { name: 'Ready' })).toBeTruthy();
    expect(screen.queryByRole('menuitem', { name: 'Blocked' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'Completed' })).toBeNull();
  });

  it('keeps the status a selected task is already in', async () => {
    await openMoveMenu(['failed', 'ready']);

    expect(screen.getByRole('menuitem', { name: 'Ready' })).toBeTruthy();
  });

  it('fails open when the selected tasks cannot be resolved to statuses', async () => {
    await openMoveMenu([]);

    expect(screen.getByRole('menuitem', { name: 'Ready' })).toBeTruthy();
    expect(screen.getByRole('menuitem', { name: 'Blocked' })).toBeTruthy();
    expect(screen.getByRole('menuitem', { name: 'Completed' })).toBeTruthy();
  });
});

describe('KanbanBulkActionBar menus', () => {
  const AGENTS = [
    { id: 'agent-a', name: 'Ledger Analyst' },
    { id: 'agent-b', name: 'Report Writer' },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the menus outside the bar, so the bar overflow can never clip them', async () => {
    const user = userEvent.setup();
    renderBar(['ready', 'blocked'], AGENTS);

    await user.click(screen.getByRole('button', { name: 'Move to' }));
    expect(screen.getByTestId('kanban-bulk-bar').contains(screen.getByRole('menu'))).toBe(false);
    await user.keyboard('{Escape}');

    await user.click(screen.getByRole('button', { name: 'Reassign' }));
    expect(screen.getByTestId('kanban-bulk-bar').contains(screen.getByRole('menu'))).toBe(false);
  });

  it('closes an open menu on Escape or an outside click and keeps the bar', async () => {
    // A modal Radix menu disables pointer events on the page while it is open, so the outside click is dispatched unchecked.
    const user = userEvent.setup({ pointerEventsCheck: PointerEventsCheckLevel.Never });
    renderBar();

    await user.click(screen.getByRole('button', { name: 'Move to' }));
    expect(screen.getByRole('menu')).toBeTruthy();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());

    await user.click(screen.getByRole('button', { name: 'Reassign' }));
    expect(screen.getByRole('menu')).toBeTruthy();
    await user.click(document.body);
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());

    expect(screen.getByTestId('kanban-bulk-bar')).toBeTruthy();
    expect(bulkAction).not.toHaveBeenCalled();
  });

  it('reassigns the whole selection to the chosen agent', async () => {
    const user = userEvent.setup();
    renderBar(['ready', 'blocked'], AGENTS);

    await user.click(screen.getByRole('button', { name: 'Reassign' }));
    await user.click(screen.getByRole('menuitem', { name: 'Report Writer' }));

    await waitFor(() =>
      expect(bulkAction).toHaveBeenCalledWith('board-1', ['t1', 't2'], 'reassign', { agent_id: 'agent-b' }, false),
    );
  });

  it('Unassigned sends an empty agent id', async () => {
    const user = userEvent.setup();
    renderBar(['ready', 'blocked'], AGENTS);

    await user.click(screen.getByRole('button', { name: 'Reassign' }));
    await user.click(screen.getByRole('menuitem', { name: 'Unassigned' }));

    await waitFor(() =>
      expect(bulkAction).toHaveBeenCalledWith('board-1', ['t1', 't2'], 'reassign', { agent_id: '' }, false),
    );
  });

  it('locks both menu triggers while a request is in flight', async () => {
    let finish: (value: { results: []; total: number; succeeded: number; failed: number }) => void = () => {};
    vi.mocked(bulkAction).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const user = userEvent.setup();
    renderBar();

    await user.click(screen.getByRole('button', { name: 'Move to' }));
    await user.click(screen.getByRole('menuitem', { name: 'Ready' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Move to' })).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Reassign' })).toBeDisabled();
    expect(bulkAction).toHaveBeenCalledTimes(1);

    finish({ results: [], total: 2, succeeded: 2, failed: 0 });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Move to' })).toBeEnabled());
  });
});
