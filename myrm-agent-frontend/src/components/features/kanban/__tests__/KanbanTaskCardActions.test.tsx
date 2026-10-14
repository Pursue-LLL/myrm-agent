import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import KanbanTaskCardActions from '../KanbanTaskCardActions';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

function makeTask(status: TaskStatus): KanbanTask {
  return {
    task_id: 'task-1',
    board_id: 'board-1',
    title: 'Task',
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

function renderActions(status: TaskStatus, overrides: Partial<Parameters<typeof KanbanTaskCardActions>[0]> = {}) {
  const handlers = {
    onMove: vi.fn(),
    onDelete: vi.fn(),
    onSpecify: vi.fn(),
    onDecompose: vi.fn(),
  };
  render(<KanbanTaskCardActions task={makeTask(status)} {...handlers} {...overrides} />);
  return handlers;
}

const trigger = () => screen.getByRole('button', { name: 'cardActions' });

describe('KanbanTaskCardActions trigger', () => {
  it('stays in the DOM and is revealed on hover, keyboard focus and touch', () => {
    renderActions('ready');
    const classes = trigger().className.split(/\s+/);
    expect(classes).toEqual(
      expect.arrayContaining([
        'opacity-0',
        'group-hover:opacity-100',
        'group-focus-within:opacity-100',
        'pointer-coarse:opacity-100',
      ]),
    );
  });
});

describe('KanbanTaskCardActions menu', () => {
  it('opens from the keyboard and lists the transitions allowed for the status', async () => {
    const user = userEvent.setup();
    renderActions('ready');

    trigger().focus();
    await user.keyboard('{Enter}');

    const labels = screen.getAllByRole('menuitem').map((item) => item.textContent);
    expect(labels).toEqual(['moveTo.running', 'moveTo.blocked', 'moveTo.archived', 'deleteAction']);
  });

  it('runs the handler of the selected item', async () => {
    const user = userEvent.setup();
    const onOpenTaskDrawer = vi.fn();
    const { onMove, onDelete } = renderActions('ready', { onOpenTaskDrawer });

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: 'taskDetails' }));
    expect(onOpenTaskDrawer).toHaveBeenCalledWith('task-1');

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: 'moveTo.running' }));
    expect(onMove).toHaveBeenCalledWith('task-1', 'running');

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: 'deleteAction' }));
    expect(onDelete).toHaveBeenCalledWith('task-1');
  });

  it('offers Specify and Decompose only for a triage task', async () => {
    const user = userEvent.setup();
    const { onSpecify, onDecompose } = renderActions('triage');

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: 'specify' }));
    expect(onSpecify).toHaveBeenCalledTimes(1);

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: 'decompose' }));
    expect(onDecompose).toHaveBeenCalledTimes(1);
  });

  it('does not offer Specify, Decompose or Reclaim outside their statuses', async () => {
    const user = userEvent.setup();
    renderActions('ready', { onReclaim: vi.fn() });

    await user.click(trigger());

    expect(screen.queryByRole('menuitem', { name: 'specify' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'decompose' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'reclaimConfirm' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'taskDetails' })).toBeNull();
  });

  it('offers Reclaim for a running task only when a handler is provided', async () => {
    const user = userEvent.setup();
    const onReclaim = vi.fn();
    renderActions('running', { onReclaim });

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: 'reclaimConfirm' }));

    expect(onReclaim).toHaveBeenCalledWith('task-1');
  });

  it('omits Reclaim for a running task without a handler', async () => {
    const user = userEvent.setup();
    renderActions('running');

    await user.click(trigger());

    expect(screen.queryByRole('menuitem', { name: 'reclaimConfirm' })).toBeNull();
  });
});

describe('KanbanTaskCardActions inside a draggable card', () => {
  function renderInsideCard() {
    const card = { onClick: vi.fn(), onDoubleClick: vi.fn(), onPointerDown: vi.fn() };
    const handlers = { onMove: vi.fn(), onDelete: vi.fn(), onSpecify: vi.fn(), onDecompose: vi.fn() };
    render(
      // The wrapper stands in for the dnd-kit draggable card, which listens for pointer, click and double-click.
      <div
        role="presentation"
        onClick={card.onClick}
        onDoubleClick={card.onDoubleClick}
        onPointerDown={card.onPointerDown}
      >
        <KanbanTaskCardActions task={makeTask('ready')} {...handlers} />
      </div>,
    );
    return card;
  }

  it('keeps pointer gestures on the trigger away from the card', async () => {
    // The open modal menu sets `pointer-events: none` on the page, which the second click of a double-click hits.
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const card = renderInsideCard();

    const button = trigger();
    await user.dblClick(button);

    expect(card.onPointerDown).not.toHaveBeenCalled();
    expect(card.onClick).not.toHaveBeenCalled();
    expect(card.onDoubleClick).not.toHaveBeenCalled();
  });

  it('keeps pointer gestures inside the portaled menu away from the card', async () => {
    const user = userEvent.setup();
    const card = renderInsideCard();

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: 'moveTo.running' }));

    expect(card.onPointerDown).not.toHaveBeenCalled();
    expect(card.onClick).not.toHaveBeenCalled();
  });
});
