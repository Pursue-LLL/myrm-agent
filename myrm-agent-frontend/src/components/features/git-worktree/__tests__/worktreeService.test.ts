import { describe, it, expect, vi, beforeEach } from 'vitest';
import { worktreeService } from '../worktreeService';
import { WorktreeRequestError } from '../worktreeErrors';
import { ApiError, apiRequest } from '@/lib/api';

vi.mock('@/lib/api', () => {
  class MockApiError extends Error {
    constructor(
      message: string,
      public code: number,
      public details: unknown[],
      public traceId: string | undefined,
      public businessCode?: string,
    ) {
      super(message);
    }
  }
  return { apiRequest: vi.fn(), ApiError: MockApiError };
});

describe('worktreeService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists worktrees via apiRequest on success', async () => {
    const mockList = [
      {
        path: '/repo/main',
        branch: 'main',
        head_commit: '123456',
        is_current: true,
        is_bare: false,
        is_dirty: false,
        is_locked: false,
        lock_reason: null,
      },
    ];
    vi.mocked(apiRequest).mockResolvedValueOnce(mockList);

    const result = await worktreeService.listWorktrees();
    expect(apiRequest).toHaveBeenCalledWith('/git/worktrees');
    expect(result).toEqual(mockList);
  });

  it('falls back to default worktrees on apiRequest failure', async () => {
    vi.mocked(apiRequest).mockRejectedValueOnce(new Error('Network error'));

    const result = await worktreeService.listWorktrees();
    expect(result.length).toBeGreaterThan(0);
    expect(result[0].branch).toBe('main');
  });

  it('creates worktree successfully', async () => {
    const created = {
      path: '/repo/.worktrees/feature-x',
      branch: 'feature-x',
      head_commit: 'abcdef',
      is_current: true,
      is_bare: false,
      is_dirty: false,
      is_locked: false,
      lock_reason: null,
    };
    vi.mocked(apiRequest).mockResolvedValueOnce(created);

    const res = await worktreeService.createWorktree({ branch: 'feature-x' });
    expect(apiRequest).toHaveBeenCalledWith(
      '/git/worktrees',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(res).toEqual(created);
  });

  it('creates without the global error toast, the caller words the failure itself', async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({ path: '/repo/.worktrees/x', branch: 'x' });

    await worktreeService.createWorktree({ branch: 'x' });

    expect(apiRequest).toHaveBeenCalledWith('/git/worktrees', expect.objectContaining({ silent: true }));
  });

  it('rejects with the server failure code instead of faking a created worktree', async () => {
    vi.mocked(apiRequest).mockRejectedValueOnce(
      new ApiError('Failed to create worktree: unsafe', 400, [], undefined, 'unsafe-repository'),
    );

    const failure = await worktreeService.createWorktree({ branch: 'lane' }).catch((err: unknown) => err);

    expect(failure).toBeInstanceOf(WorktreeRequestError);
    expect((failure as WorktreeRequestError).reason).toBe('unsafe-repository');
  });

  it.each([
    ['an unknown server code', new ApiError('boom', 500, [], undefined, 'something-new')],
    ['a response without a code', new ApiError('boom', 500)],
    ['a network failure', new Error('Failed to fetch')],
  ])('maps %s to the generic failure and never to a created worktree', async (_label, error) => {
    vi.mocked(apiRequest).mockRejectedValueOnce(error);

    const failure = await worktreeService.createWorktree({ branch: 'lane' }).catch((err: unknown) => err);

    expect(failure).toBeInstanceOf(WorktreeRequestError);
    expect((failure as WorktreeRequestError).reason).toBe('error');
  });

  it('switches worktree successfully', async () => {
    const switched = {
      path: '/repo/.worktrees/feature-y',
      branch: 'feature-y',
      head_commit: '987654',
      is_current: true,
      is_bare: false,
      is_dirty: false,
      is_locked: false,
      lock_reason: null,
    };
    vi.mocked(apiRequest).mockResolvedValueOnce(switched);

    const res = await worktreeService.switchWorktree('/repo/.worktrees/feature-y');
    expect(res.path).toBe('/repo/.worktrees/feature-y');
  });

  it('gets and binds session checkout anchor metadata', async () => {
    const anchor = {
      session_id: 'session-123',
      project_root: '/repo',
      worktree_path: '/repo/.worktrees/task-1',
      checkout_ref: 'task-1',
      is_anchored: true,
      active_worktree_path: '/repo/.worktrees/task-1',
      touched_files: [{ file_path: 'app.ts', change_type: 'modified', touched_at: '2026-09-02T10:00:00Z' }],
      created_at: '2026-09-02T10:00:00Z',
    };
    vi.mocked(apiRequest).mockResolvedValueOnce(anchor);

    const res = await worktreeService.getSessionCheckoutAnchor('session-123');
    expect(res.session_id).toBe('session-123');
    expect(res.touched_files.length).toBe(1);
  });
});
