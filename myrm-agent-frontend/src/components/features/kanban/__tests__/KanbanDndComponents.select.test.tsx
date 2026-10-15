import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DndContext } from '@dnd-kit/core';
import type { useTranslations } from 'next-intl';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { KanbanDropColumn } from '../KanbanDndComponents';

const stableT = (key: string, values?: Record<string, string>) => (values?.title ? `${key}:${values.title}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('../KanbanTaskCard', () => ({
  default: ({ task }: { task: KanbanTask }) => <p>{task.title}</p>,
}));

function makeTask(id: string): KanbanTask {
  return {
    task_id: id,
    board_id: 'board-1',
    title: `Title ${id}`,
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
}

const tasks = [makeTask('a'), makeTask('b')];

/** 监听 document 上的 keydown 是否被 preventDefault（晚于 React 根与 dnd-kit 的处理）。 */
function trackKeydownPrevented(key: string) {
  const prevented: boolean[] = [];
  const listener = (event: KeyboardEvent) => {
    if (event.key === key) {
      prevented.push(event.defaultPrevented);
    }
  };
  document.addEventListener('keydown', listener);
  return { prevented, stop: () => document.removeEventListener('keydown', listener) };
}

function renderColumn(selectedTaskIds: string[] = []) {
  const onTaskSelect = vi.fn();
  const onOpenTaskDrawer = vi.fn();
  const onDragStart = vi.fn();
  render(
    <DndContext onDragStart={onDragStart}>
      <KanbanDropColumn
        status="ready"
        tasks={tasks}
        allTasks={tasks}
        draggedTaskId={null}
        dragOverColumn={null}
        selectedTaskIds={selectedTaskIds}
        onTaskSelect={onTaskSelect}
        onMoveTask={vi.fn()}
        onDeleteTask={vi.fn()}
        onReclaimTask={vi.fn()}
        onRefresh={vi.fn()}
        onOpenTaskDrawer={onOpenTaskDrawer}
        t={stableT as unknown as ReturnType<typeof useTranslations<'kanban'>>}
      />
    </DndContext>,
  );
  return { onTaskSelect, onOpenTaskDrawer, onDragStart };
}

describe('DraggableTaskCard selection checkbox', () => {
  let tracker: ReturnType<typeof trackKeydownPrevented> | undefined;

  afterEach(() => tracker?.stop());

  it('labels each checkbox with its task title and reflects the selected state', () => {
    renderColumn(['a']);

    expect(screen.getByRole('checkbox', { name: 'selectTask:Title a' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'selectTask:Title b' })).not.toBeChecked();
  });

  it('toggles selection on a plain click without opening the drawer', async () => {
    const { onTaskSelect, onOpenTaskDrawer } = renderColumn();
    const user = userEvent.setup();

    await user.click(screen.getByRole('checkbox', { name: 'selectTask:Title a' }));

    expect(onTaskSelect).toHaveBeenCalledTimes(1);
    expect(onTaskSelect.mock.calls[0]?.[0]).toBe('a');
    expect(onOpenTaskDrawer).not.toHaveBeenCalled();
  });

  it('does not open the drawer on a double click of the checkbox', async () => {
    const { onTaskSelect, onOpenTaskDrawer } = renderColumn();
    const user = userEvent.setup();

    await user.dblClick(screen.getByRole('checkbox', { name: 'selectTask:Title a' }));

    expect(onTaskSelect).toHaveBeenCalledTimes(2);
    expect(onOpenTaskDrawer).not.toHaveBeenCalled();
  });

  it('forwards Shift to the selection handler so ranges keep working', async () => {
    const { onTaskSelect } = renderColumn(['a']);
    const user = userEvent.setup();

    await user.keyboard('{Shift>}');
    await user.click(screen.getByRole('checkbox', { name: 'selectTask:Title b' }));
    await user.keyboard('{/Shift}');

    expect(onTaskSelect).toHaveBeenCalledTimes(1);
    expect(onTaskSelect.mock.calls[0]?.[0]).toBe('b');
    expect(onTaskSelect.mock.calls[0]?.[1]).toMatchObject({ shiftKey: true });
  });

  it('lets Space toggle the focused checkbox instead of starting a keyboard drag', async () => {
    const { onTaskSelect, onOpenTaskDrawer, onDragStart } = renderColumn();
    tracker = trackKeydownPrevented(' ');
    const user = userEvent.setup();

    screen.getByRole('checkbox', { name: 'selectTask:Title a' }).focus();
    await user.keyboard(' ');

    expect(onTaskSelect).toHaveBeenCalledTimes(1);
    expect(onTaskSelect.mock.calls[0]?.[0]).toBe('a');
    expect(tracker.prevented).toEqual([false]);
    expect(onDragStart).not.toHaveBeenCalled();
    expect(onOpenTaskDrawer).not.toHaveBeenCalled();
  });

  it('keeps Enter inert on the checkbox (checkbox semantics): no toggle, no drag, no drawer', async () => {
    const { onTaskSelect, onOpenTaskDrawer, onDragStart } = renderColumn();
    const user = userEvent.setup();

    screen.getByRole('checkbox', { name: 'selectTask:Title a' }).focus();
    await user.keyboard('{Enter}');

    expect(onTaskSelect).not.toHaveBeenCalled();
    expect(onDragStart).not.toHaveBeenCalled();
    expect(onOpenTaskDrawer).not.toHaveBeenCalled();
  });

  it('reveals the checkbox through hover, keyboard focus and touch while nothing is selected', () => {
    renderColumn();
    const idleBox = screen.getByRole('checkbox', { name: 'selectTask:Title b' });
    expect(idleBox.className).toContain('opacity-0');
    expect(idleBox.className).toContain('group-focus-within/select:opacity-100');
    expect(idleBox.className).toContain('pointer-coarse:opacity-100');
  });

  it('forces the ring colour past the unlayered global border rule so an unchecked circle stays visible', () => {
    renderColumn(['a']);

    const box = screen.getByRole('checkbox', { name: 'selectTask:Title b' });
    expect(box.className).toContain('!border-primary');
  });

  it('shows unselected checkboxes permanently while a selection exists', () => {
    renderColumn(['a']);

    const otherBox = screen.getByRole('checkbox', { name: 'selectTask:Title b' });
    expect(otherBox.className).toContain('opacity-100');
    expect(otherBox.className).not.toContain('opacity-0');
  });
});
