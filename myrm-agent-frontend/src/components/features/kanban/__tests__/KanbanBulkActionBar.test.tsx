/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

function renderBar(selectedStatuses: TaskStatus[] = ['ready', 'blocked']) {
  const onClear = vi.fn();
  const onComplete = vi.fn();
  render(
    <KanbanBulkActionBar
      boardId="board-1"
      selectedIds={['t1', 't2']}
      selectedStatuses={selectedStatuses}
      onClear={onClear}
      onComplete={onComplete}
      agents={[]}
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

    expect(screen.getByRole('button', { name: 'Ready' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Blocked' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Completed' })).toBeTruthy();

    await user.click(screen.getByRole('button', { name: 'Blocked' }));

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

    expect(screen.getByRole('button', { name: 'Ready' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Blocked' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Completed' })).toBeNull();
  });

  it('keeps the status a selected task is already in', async () => {
    await openMoveMenu(['failed', 'ready']);

    expect(screen.getByRole('button', { name: 'Ready' })).toBeTruthy();
  });

  it('fails open when the selected tasks cannot be resolved to statuses', async () => {
    await openMoveMenu([]);

    expect(screen.getByRole('button', { name: 'Ready' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Blocked' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Completed' })).toBeTruthy();
  });
});
