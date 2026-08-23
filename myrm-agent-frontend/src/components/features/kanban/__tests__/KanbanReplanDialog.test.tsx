import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import KanbanReplanDialog from '../KanbanReplanDialog';
import type { KanbanBoard, PlanRevisionItem } from '@/services/kanban';
import * as kanbanService from '@/services/kanban';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/services/kanban', () => ({
  reviseBoardPlan: vi.fn(),
}));

describe('KanbanReplanDialog', () => {
  const mockBoard: KanbanBoard = {
    board_id: 'board-123',
    name: 'Test Board',
    description: 'A test board',
    settings: {
      max_concurrent_tasks: 3,
      heartbeat_interval_seconds: 30,
      zombie_timeout_seconds: 120,
      max_retries_per_task: 3,
      auto_block_after_consecutive_failures: 5,
      specify_max_tokens: 6000,
      auto_specify_on_create: false,
    },
    created_at: '2026-08-22T00:00:00Z',
    updated_at: '2026-08-22T00:00:00Z',
  };

  const proposedChanges: PlanRevisionItem[] = [
    {
      action: 'add',
      task_id: 't-new-1',
      title: 'Analyze Root Cause',
      description: 'Trace stack traces',
    },
    {
      action: 'update',
      task_id: 't-up-1',
      title: 'Fix Engine Bug',
    },
    {
      action: 'remove',
      task_id: 't-del-1',
      title: 'Legacy Step',
    },
  ];

  it('renders diff changes and badges correctly', () => {
    render(
      <KanbanReplanDialog
        board={mockBoard}
        open={true}
        onOpenChange={vi.fn()}
        proposedChanges={proposedChanges}
      />
    );

    expect(screen.getByText('Analyze Root Cause')).toBeInTheDocument();
    expect(screen.getByText('Fix Engine Bug')).toBeInTheDocument();
    expect(screen.getByText('Legacy Step')).toBeInTheDocument();
    expect(screen.getByText('ADD')).toBeInTheDocument();
    expect(screen.getByText('UPDATE')).toBeInTheDocument();
    expect(screen.getByText('REMOVE')).toBeInTheDocument();
  });

  it('submits revision and invokes onApplied on success', async () => {
    const onOpenChange = vi.fn();
    const onApplied = vi.fn();
    vi.mocked(kanbanService.reviseBoardPlan).mockResolvedValueOnce({
      ok: true,
      board_id: 'board-123',
      reason: 'applied',
      added_task_ids: ['t-new-1'],
      updated_task_ids: ['t-up-1'],
      removed_task_ids: ['t-del-1'],
      added_edges: [],
      removed_edges: [],
      persisted: true,
    });

    render(
      <KanbanReplanDialog
        board={mockBoard}
        open={true}
        onOpenChange={onOpenChange}
        proposedChanges={proposedChanges}
        defaultRationale="Discovered new defect path"
        onApplied={onApplied}
      />
    );

    const applyButton = screen.getByRole('button', { name: /replanApply/i });
    fireEvent.click(applyButton);

    await waitFor(() => {
      expect(kanbanService.reviseBoardPlan).toHaveBeenCalledWith(
        'board-123',
        expect.objectContaining({
          board_id: 'board-123',
          rationale: 'Discovered new defect path',
          task_changes: proposedChanges,
        })
      );
      expect(onOpenChange).toHaveBeenCalledWith(false);
      expect(onApplied).toHaveBeenCalled();
    });
  });
});
