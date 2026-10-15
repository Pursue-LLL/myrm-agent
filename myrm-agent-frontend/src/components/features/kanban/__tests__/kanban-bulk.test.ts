import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { bulkAction } from '@/services/kanban';
import messages from '../../../../../locales/en.json';
import { BULK_CHUNK_SIZE, runBulkAction } from '../kanban-bulk';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/kanban', () => ({ bulkAction: vi.fn() }));

type RunOptions = Parameters<typeof runBulkAction>[0];

const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

const t = createTranslator({ locale: 'en', messages, namespace: 'kanban' }) as unknown as RunOptions['t'];

const ids = (count: number) => Array.from({ length: count }, (_, i) => `t${i}`);

/** 服务端的逐条结果：`rejected` 里的任务被拒，其余成功。 */
const serverAnswer =
  (rejected: ReadonlySet<string> = new Set()): typeof bulkAction =>
  async (_board, taskIds) => {
    const results = taskIds.map((taskId) => ({ task_id: taskId, success: !rejected.has(taskId) }));
    const failed = results.filter((r) => !r.success).length;
    return { results, total: results.length, succeeded: results.length - failed, failed };
  };

const answerEachChunk = (rejected?: ReadonlySet<string>) =>
  vi.mocked(bulkAction).mockImplementation(serverAnswer(rejected));

const run = (taskIds: string[]) =>
  runBulkAction({ boardId: 'board-1', taskIds, action: 'move', params: { status: 'ready' }, t });

const sentChunks = () => vi.mocked(bulkAction).mock.calls.map((call) => call[1]);

describe('runBulkAction chunking', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('sends nothing and shows no toast for an empty selection', async () => {
    await expect(run([])).resolves.toEqual([]);

    expect(bulkAction).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.warning).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('sends a selection that fits in one chunk as a single request', async () => {
    answerEachChunk();

    await expect(run(ids(BULK_CHUNK_SIZE))).resolves.toEqual([]);

    expect(sentChunks()).toEqual([ids(BULK_CHUNK_SIZE)]);
    expect(toast.success).toHaveBeenCalledWith(`${BULK_CHUNK_SIZE} tasks updated`);
  });

  it('splits a larger selection into ordered chunks of at most BULK_CHUNK_SIZE', async () => {
    answerEachChunk();
    const selection = ids(BULK_CHUNK_SIZE * 5 + 8);

    await run(selection);

    const chunks = sentChunks();
    expect(chunks.map((chunk) => chunk.length)).toEqual([25, 25, 25, 25, 25, 8]);
    expect(chunks.flat()).toEqual(selection);
  });

  it('starts a second chunk with the first task past the boundary', async () => {
    answerEachChunk();

    await run(ids(BULK_CHUNK_SIZE + 1));

    expect(sentChunks().map((chunk) => chunk.length)).toEqual([BULK_CHUNK_SIZE, 1]);
  });

  it('passes the action, params and confirm flag to every chunk', async () => {
    answerEachChunk();
    const params = { status: 'ready' };

    await runBulkAction({ boardId: 'board-1', taskIds: ids(30), action: 'move', params, confirm: true, t });

    expect(bulkAction).toHaveBeenNthCalledWith(1, 'board-1', ids(30).slice(0, 25), 'move', params, true);
    expect(bulkAction).toHaveBeenNthCalledWith(2, 'board-1', ids(30).slice(25), 'move', params, true);
  });

  it('reports one summary for the whole selection instead of one per chunk', async () => {
    answerEachChunk();

    await run(ids(133));

    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith('133 tasks updated');
    expect(toast.warning).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('merges the tasks the server rejected in different chunks', async () => {
    answerEachChunk(new Set(['t3', 't40']));

    await expect(run(ids(60))).resolves.toEqual(['t3', 't40']);

    expect(toast.warning).toHaveBeenCalledTimes(1);
    expect(toast.warning).toHaveBeenCalledWith('58 succeeded, 2 failed');
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('returns null with the localized error when the first chunk fails, and sends nothing more', async () => {
    vi.mocked(bulkAction).mockRejectedValue(new Error('network down'));

    await expect(run(ids(60))).resolves.toBeNull();

    expect(bulkAction).toHaveBeenCalledTimes(1);
    expect(toast.error).toHaveBeenCalledWith('Failed to update task');
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it('keeps the confirmed chunks and returns the failed chunk plus the rest when a later chunk fails', async () => {
    const answer = serverAnswer(new Set(['t3']));
    vi.mocked(bulkAction).mockImplementation(async (...args) => {
      if (args[1][0] === 't50') {
        throw new Error('request timed out');
      }
      return answer(...args);
    });

    const unconfirmed = await run(ids(110));

    expect(sentChunks().map((chunk) => chunk[0])).toEqual(['t0', 't25', 't50']);
    expect(unconfirmed).toEqual(['t3', ...ids(110).slice(50)]);
    expect(toast.warning).toHaveBeenCalledWith('49 succeeded, 61 failed');
    expect(toast.error).not.toHaveBeenCalled();
  });
});
