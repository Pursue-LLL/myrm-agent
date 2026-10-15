import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DndContext } from '@dnd-kit/core';
import type { useTranslations } from 'next-intl';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { expectNonNull } from '@/test-utils/expectDefined';
import { KanbanDropColumn } from '../KanbanDndComponents';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('../KanbanTaskCard', () => ({
  default: ({ task }: { task: KanbanTask }) => (
    <button type="button" data-testid={`inner-button-${task.task_id}`}>
      {task.title}
    </button>
  ),
}));

const task: KanbanTask = {
  task_id: 'task-1',
  board_id: 'board-1',
  title: 'Task',
  description: '',
  status: 'ready' as TaskStatus,
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

/** 真实 dnd-kit：记录 Enter 的 keydown 是否被 preventDefault（监听挂在 document，晚于 React 根处理）。 */
function trackEnterPrevented() {
  const prevented: boolean[] = [];
  const listener = (event: KeyboardEvent) => {
    if (event.key === 'Enter') {
      prevented.push(event.defaultPrevented);
    }
  };
  document.addEventListener('keydown', listener);
  return { prevented, stop: () => document.removeEventListener('keydown', listener) };
}

function renderBoardColumn() {
  render(
    <DndContext>
      <KanbanDropColumn
        status="ready"
        tasks={[task]}
        allTasks={[task]}
        draggedTaskId={null}
        dragOverColumn={null}
        selectedTaskIds={[]}
        onTaskSelect={vi.fn()}
        onMoveTask={vi.fn()}
        onDeleteTask={vi.fn()}
        onReclaimTask={vi.fn()}
        onRefresh={vi.fn()}
        t={stableT as ReturnType<typeof useTranslations<'kanban'>>}
      />
    </DndContext>,
  );
}

describe('DraggableTaskCard keyboard activation', () => {
  let tracker: ReturnType<typeof trackEnterPrevented>;

  afterEach(() => tracker.stop());

  it('lets a button inside the card handle Enter instead of starting a drag', async () => {
    renderBoardColumn();
    tracker = trackEnterPrevented();
    const user = userEvent.setup();

    screen.getByTestId('inner-button-task-1').focus();
    await user.keyboard('{Enter}');

    expect(tracker.prevented).toEqual([false]);
  });

  it('still starts a keyboard drag when the card itself has focus', async () => {
    renderBoardColumn();
    tracker = trackEnterPrevented();
    const user = userEvent.setup();

    const card = document.querySelector<HTMLElement>('[aria-roledescription="draggable"]');
    expectNonNull(card, 'draggable card');
    card.focus();
    await user.keyboard('{Enter}');

    expect(tracker.prevented).toEqual([true]);
  });
});
