import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import RaceSection from '../RaceSection';
import type { KanbanTask } from '@/services/kanban';
import * as kanbanService from '@/services/kanban';

vi.mock('@/services/kanban', () => ({
  raceLanes: vi.fn(),
  raceEstimate: vi.fn(),
  raceStart: vi.fn(),
  raceDecide: vi.fn(),
}));

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
}));

vi.mock('@/store/useAgentStore', () => ({
  default: (selector: (state: { agents: never[]; fetchAgents: () => void }) => unknown) =>
    selector({ agents: [], fetchAgents: vi.fn() }),
}));

const stableT = (key: string) => key;

function makeTask(overrides: Partial<KanbanTask> = {}): KanbanTask {
  return {
    task_id: 'parent-1',
    board_id: 'board-1',
    title: 'Fix retry',
    description: 'Make it idempotent',
    status: 'backlog',
    priority: 'normal',
    branch: 'feature/retry',
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
    ...overrides,
  } as KanbanTask;
}

describe('RaceSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the start form when no lanes exist and the task has a branch', async () => {
    vi.mocked(kanbanService.raceLanes).mockResolvedValue({ parent_task_id: 'parent-1', lanes: [] });
    vi.mocked(kanbanService.raceEstimate).mockResolvedValue({
      lanes: 3,
      per_lane_avg_tokens: 1000,
      total_tokens: 3000,
      based_on_completed_tasks: 2,
    });
    const onChanged = vi.fn();
    render(<RaceSection boardId="board-1" task={makeTask()} onChanged={onChanged} t={stableT} />);

    await waitFor(() => expect(screen.getByTestId('race-section')).toBeInTheDocument());
    expect(screen.getByText('raceStart')).toBeDisabled();

    fireEvent.click(screen.getByText('raceConfirmCost'));
    fireEvent.click(screen.getByText('raceStart'));

    await waitFor(() =>
      expect(kanbanService.raceStart).toHaveBeenCalledWith('board-1', 'parent-1', {
        lanes: [
          { instruction_variant: undefined },
          { instruction_variant: undefined },
          { instruction_variant: undefined },
        ],
        confirm_cost: true,
      }),
    );
    expect(onChanged).toHaveBeenCalled();
  });

  it('shows a branch hint when the task has no branch', async () => {
    vi.mocked(kanbanService.raceLanes).mockResolvedValue({ parent_task_id: 'parent-1', lanes: [] });
    render(<RaceSection boardId="board-1" task={makeTask({ branch: null })} onChanged={vi.fn()} t={stableT} />);
    await waitFor(() => expect(screen.getByText('raceNeedsBranch')).toBeInTheDocument());
  });

  it('lists lanes and decides the winner', async () => {
    vi.mocked(kanbanService.raceLanes).mockResolvedValue({
      parent_task_id: 'parent-1',
      lanes: [
        {
          task_id: 'lane-a',
          title: 'Fix retry（方案A）',
          status: 'in_review',
          agent_id: null,
          branch: 'feature/retry',
          result: 'done A',
          total_tokens: 1200,
        },
        {
          task_id: 'lane-b',
          title: 'Fix retry（方案B）',
          status: 'running',
          agent_id: null,
          branch: 'feature/retry',
          result: '',
          total_tokens: 0,
        },
      ],
    });
    vi.mocked(kanbanService.raceDecide).mockResolvedValue({
      parent_task_id: 'parent-1',
      winner_task_id: 'lane-a',
      archived_lane_ids: ['lane-b'],
    });
    const onChanged = vi.fn();
    render(<RaceSection boardId="board-1" task={makeTask()} onChanged={onChanged} t={stableT} />);

    await waitFor(() => expect(screen.getByText('Fix retry（方案A）')).toBeInTheDocument());
    fireEvent.click(screen.getByText('racePickWinner'));
    await waitFor(() =>
      expect(kanbanService.raceDecide).toHaveBeenCalledWith('board-1', 'parent-1', {
        winner_task_id: 'lane-a',
      }),
    );
    expect(onChanged).toHaveBeenCalled();
  });
});
