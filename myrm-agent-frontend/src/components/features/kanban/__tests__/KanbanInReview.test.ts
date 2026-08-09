import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EVENT_KIND_STYLES, NEXT_STATUSES, STATUS_DOT } from '../kanban-styles';
import { approveTask, createTask, rejectTask } from '@/services/kanban';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api';

const mockApiRequest = vi.mocked(apiRequest);

describe('kanban in_review styles', () => {
  it('in_review is a board column with no direct next status', () => {
    expect(NEXT_STATUSES.in_review).toEqual([]);
  });

  it('in_review has a distinct amber dot', () => {
    expect(STATUS_DOT.in_review).toBe('bg-amber-500');
  });

  it('maps review lifecycle event kinds to styles', () => {
    expect(EVENT_KIND_STYLES.review_requested).toMatch(/amber/);
    expect(EVENT_KIND_STYLES.approved).toBeTruthy();
    expect(EVENT_KIND_STYLES.rejected).toBeTruthy();
  });
});

describe('kanban approval API', () => {
  beforeEach(() => {
    mockApiRequest.mockReset();
    mockApiRequest.mockResolvedValue({ task_id: 't1' });
  });

  it('approveTask POSTs to /approve with approver', async () => {
    await approveTask('t1', 'alice');
    expect(mockApiRequest).toHaveBeenCalledWith('/kanban/tasks/t1/approve', {
      method: 'POST',
      body: JSON.stringify({ approver: 'alice' }),
    });
  });

  it('rejectTask POSTs to /reject with reason and approver', async () => {
    await rejectTask('t1', 'add citations', 'bob');
    expect(mockApiRequest).toHaveBeenCalledWith('/kanban/tasks/t1/reject', {
      method: 'POST',
      body: JSON.stringify({ reason: 'add citations', approver: 'bob' }),
    });
  });

  it('createTask forwards require_approval flag', async () => {
    await createTask('b1', { title: 'deploy', require_approval: true });
    const [, opts] = mockApiRequest.mock.calls[0];
    const body = opts?.body as string;
    expect(JSON.parse(body)).toMatchObject({
      title: 'deploy',
      require_approval: true,
    });
  });
});
