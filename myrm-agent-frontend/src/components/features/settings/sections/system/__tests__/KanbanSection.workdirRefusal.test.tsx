import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiError } from '@/lib/api';
import type { KanbanBoard } from '@/services/kanban';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/services/kanban', () => ({
  listBoards: vi.fn(),
  createBoard: vi.fn(),
  updateBoard: vi.fn(),
  deleteBoard: vi.fn(),
  getBoardSummary: vi.fn(),
}));

vi.mock('@/components/features/kanban/KanbanBoardView', () => ({ default: () => null }));

import { toast } from 'sonner';
import { createBoard, listBoards, updateBoard } from '@/services/kanban';
import KanbanSection from '../KanbanSection';

const refused = (field: string, issue: string) => new ApiError('refused', 40001, [{ field, issue }]);

const board = {
  board_id: 'b1',
  name: 'Roadmap',
  description: '',
  settings: { max_concurrent_tasks: 3, default_workdir: null },
} as unknown as KanbanBoard;

async function openCreateForm(): Promise<void> {
  fireEvent.click(await screen.findByText('+ kanban.createBoard'));
  fireEvent.change(screen.getByPlaceholderText('kanban.boardNamePlaceholder'), { target: { value: 'Docs' } });
  fireEvent.change(screen.getByPlaceholderText('kanban.defaultWorkdirPlaceholder'), { target: { value: '/Users/me' } });
}

describe('KanbanSection default working folder refusal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listBoards).mockResolvedValue({ items: [], total: 0 } as Awaited<ReturnType<typeof listBoards>>);
  });

  it('tells the user a too-broad folder is the reason a board could not be created', async () => {
    vi.mocked(createBoard).mockRejectedValue(refused('default_workdir', 'too_broad'));
    render(<KanbanSection />);
    await openCreateForm();

    fireEvent.click(screen.getByText('kanban.create'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('common.workspacePathIssue.tooBroad'));
  });

  it('keeps the generic message for a failure that is not about the folder', async () => {
    vi.mocked(createBoard).mockRejectedValue(new ApiError('boom'));
    render(<KanbanSection />);
    await openCreateForm();

    fireEvent.click(screen.getByText('kanban.create'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('kanban.createBoardError'));
  });

  it('tells the user a protected folder is the reason a board could not be updated', async () => {
    vi.mocked(listBoards).mockResolvedValue({ items: [board], total: 1 } as Awaited<ReturnType<typeof listBoards>>);
    vi.mocked(updateBoard).mockRejectedValue(refused('default_workdir', 'dangerous'));
    render(<KanbanSection />);

    fireEvent.click(await screen.findByText('kanban.edit'));
    fireEvent.click(screen.getByText('kanban.save'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('common.workspacePathIssue.dangerous'));
  });
});
