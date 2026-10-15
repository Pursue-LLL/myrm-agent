import { renderHook } from '@testing-library/react';
import type { Active, Over } from '@dnd-kit/core/dist/store';
import { describe, expect, it, vi } from 'vitest';

import type { KanbanTask } from '@/services/kanban';
import { useKanbanDnD } from '../useKanbanDnD';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

const TASK_ID = 'a1b2c3d4e5f6';
const OTHER_ID = 'f6e5d4c3b2a1';
const tasks = [
  { task_id: TASK_ID, title: '修复登录', status: 'backlog' } as KanbanTask,
  { task_id: OTHER_ID, title: '补充测试', status: 'backlog' } as KanbanTask,
];

function announcements(selectedTaskIds: string[] = []) {
  const { result } = renderHook(() =>
    useKanbanDnD({ tasks, selectedTaskIds, onMoveTask: vi.fn(), onMoveBlocked: vi.fn() }),
  );
  return result.current.accessibility.announcements;
}

describe('useKanbanDnD screen reader announcements', () => {
  const active = { id: TASK_ID } as Active;
  const over = (id: string) => ({ id }) as Over;

  it('reads the task title and the localized column name instead of the task id and status enum', () => {
    const spoken = announcements();

    expect(spoken.onDragStart({ active })).toBe('已拾起“修复登录”。');
    expect(spoken.onDragOver({ active, over: over('backlog') })).toBeUndefined();
    expect(spoken.onDragOver({ active, over: over('ready') })).toBe('“修复登录”已移到“就绪”上。');
    expect(spoken.onDragOver({ active, over: over('backlog') })).toBe('“修复登录”已移到“待办”上。');
    expect(spoken.onDragEnd({ active, over: over('in_review') })).toBe('“修复登录”已放到“审核中”。');
  });

  it('falls back to a generic noun for a task or column it does not know', () => {
    const spoken = announcements();

    spoken.onDragStart({ active });
    spoken.onDragOver({ active, over: over('backlog') });

    expect(spoken.onDragOver({ active, over: over('verifying') })).toBe('“修复登录”已移到“该项”上。');
    expect(spoken.onDragStart({ active: { ...active, id: 'ghost-id' } })).toBe('已拾起“该项”。');
  });

  it('says how many cards move together when the dragged card belongs to a multi-card selection', () => {
    const spoken = announcements([TASK_ID, OTHER_ID]);

    expect(spoken.onDragStart({ active })).toBe('已拾起“修复登录, 已选 2 项”。');
    spoken.onDragOver({ active, over: over('backlog') });
    expect(spoken.onDragOver({ active, over: over('ready') })).toBe('“修复登录, 已选 2 项”已移到“就绪”上。');
    expect(spoken.onDragEnd({ active, over: over('ready') })).toBe('“修复登录, 已选 2 项”已放到“就绪”。');
  });

  it('names only the dragged card when it is outside the selection or the only one selected', () => {
    expect(announcements([OTHER_ID, 'third']).onDragStart({ active })).toBe('已拾起“修复登录”。');
    expect(announcements([TASK_ID]).onDragStart({ active })).toBe('已拾起“修复登录”。');
  });
});
