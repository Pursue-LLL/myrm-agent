/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { bulkAction } from '@/services/kanban';
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

function renderBar() {
  const onClear = vi.fn();
  const onComplete = vi.fn();
  render(
    <KanbanBulkActionBar
      boardId="board-1"
      selectedIds={['t1', 't2']}
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
