import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { KanbanTask } from '@/services/kanban';
import { getTask } from '@/services/kanban';
import { resolveTaskDepInfos } from '../resolveTaskDepInfos';

vi.mock('@/services/kanban', () => ({
  getTask: vi.fn(),
}));

const getTaskMock = vi.mocked(getTask);

function task(id: string, title: string, status: KanbanTask['status']): KanbanTask {
  return { task_id: id, title, status } as KanbanTask;
}

describe('resolveTaskDepInfos', () => {
  beforeEach(() => {
    getTaskMock.mockReset();
  });

  it('answers from the board task list without any request', async () => {
    const infos = await resolveTaskDepInfos(['a'], [task('a', 'Local A', 'running')]);

    expect(infos).toEqual([{ task_id: 'a', title: 'Local A', status: 'running' }]);
    expect(getTaskMock).not.toHaveBeenCalled();
  });

  it('fetches a task that is not on the board and keeps the input order', async () => {
    getTaskMock.mockResolvedValue(task('far', 'Remote Far', 'completed'));

    const infos = await resolveTaskDepInfos(['far', 'a'], [task('a', 'Local A', 'ready')]);

    expect(getTaskMock).toHaveBeenCalledExactlyOnceWith('far');
    expect(infos.map((info) => info.task_id)).toEqual(['far', 'a']);
    expect(infos[0]).toEqual({ task_id: 'far', title: 'Remote Far', status: 'completed' });
  });

  it('falls back to the id prefix and archived when the task cannot be fetched', async () => {
    getTaskMock.mockRejectedValue(new Error('not found'));

    const infos = await resolveTaskDepInfos(['0123456789abcdef'], []);

    expect(infos).toEqual([{ task_id: '0123456789abcdef', title: '01234567', status: 'archived' }]);
  });

  it('returns an empty list for no ids', async () => {
    expect(await resolveTaskDepInfos([], [])).toEqual([]);
  });
});
