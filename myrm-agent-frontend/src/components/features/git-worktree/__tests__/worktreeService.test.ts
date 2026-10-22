import { describe, it, expect, vi, beforeEach } from 'vitest';
import { worktreeService } from '../worktreeService';
import { apiRequest } from '@/lib/api';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

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
