import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

vi.mock('@/components/features/kanban/KanbanBoardView', () => ({
  default: ({ board }: { board: { name: string } }) => <div data-testid="board-view">{board.name}</div>,
}));

import { getBoardSummary, listBoards } from '@/services/kanban';
import KanbanSection from '../KanbanSection';

const board = {
  board_id: 'b1',
  name: 'Roadmap',
  description: 'Quarterly plan',
  settings: { max_concurrent_tasks: 3, default_workdir: null },
} as unknown as KanbanBoard;

describe('KanbanSection board row', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.mocked(listBoards).mockResolvedValue({ items: [board], total: 1 } as Awaited<ReturnType<typeof listBoards>>);
    vi.mocked(getBoardSummary).mockResolvedValue({} as Awaited<ReturnType<typeof getBoardSummary>>);
  });

  it('opens the board when its name is chosen', async () => {
    render(<KanbanSection />);

    fireEvent.click(await screen.findByRole('button', { name: /Roadmap/ }));

    expect(screen.getByTestId('board-view')).toHaveTextContent('Roadmap');
  });

  it('shows the description inside the button that opens the board', async () => {
    render(<KanbanSection />);

    const open = await screen.findByRole('button', { name: /Roadmap/ });

    expect(open).toHaveTextContent('Quarterly plan');
  });

  it('edits a board without opening it', async () => {
    render(<KanbanSection />);

    fireEvent.click(await screen.findByText('kanban.edit'));

    expect(screen.getByText('kanban.save')).toBeInTheDocument();
    expect(screen.queryByTestId('board-view')).not.toBeInTheDocument();
  });

  it('asks about deleting a board without opening it', async () => {
    render(<KanbanSection />);

    fireEvent.click(await screen.findByText('\u00d7'));

    await waitFor(() => expect(getBoardSummary).toHaveBeenCalledWith('b1'));
    expect(screen.queryByTestId('board-view')).not.toBeInTheDocument();
  });
});
