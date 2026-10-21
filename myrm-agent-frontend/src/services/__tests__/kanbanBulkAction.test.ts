import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '@/lib/api';
import { bulkAction } from '@/services/kanban';

vi.mock('@/lib/api', () => ({
  API_BASE_URL: '',
  apiRequest: vi.fn(),
  fetchWithTimeout: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('bulkAction', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('posts the selection and leaves reporting a failed request to runBulkAction', async () => {
    const answer = { results: [{ task_id: 't1', success: true }], total: 1, succeeded: 1, failed: 0 };
    apiRequestMock.mockResolvedValue(answer);

    const result = await bulkAction('board-1', ['t1'], 'move', { status: 'ready' }, true);

    expect(result).toEqual(answer);
    // runBulkAction tells the user once itself; a request-level toast would report the same failure twice.
    expect(apiRequestMock).toHaveBeenCalledWith('/kanban/boards/board-1/tasks/bulk-action', {
      method: 'POST',
      body: JSON.stringify({ task_ids: ['t1'], action: 'move', params: { status: 'ready' }, confirm: true }),
      silent: true,
    });
  });

  it('sends no params and no confirmation unless asked to', async () => {
    apiRequestMock.mockResolvedValue({ results: [], total: 0, succeeded: 0, failed: 0 });

    await bulkAction('board-1', ['t1', 't2'], 'archive');

    expect(apiRequestMock).toHaveBeenCalledWith(
      '/kanban/boards/board-1/tasks/bulk-action',
      expect.objectContaining({
        body: JSON.stringify({ task_ids: ['t1', 't2'], action: 'archive', params: {}, confirm: false }),
      }),
    );
  });
});
