import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useWorktreeStore } from '../useWorktreeStore';
import { worktreeService } from '../worktreeService';

vi.mock('../worktreeService', () => ({
  worktreeService: {
    listWorktrees: vi.fn(),
    createWorktree: vi.fn(),
    switchWorktree: vi.fn(),
    removeWorktree: vi.fn(),
    getSessionCheckoutAnchor: vi.fn(),
    bindSessionCheckoutAnchor: vi.fn(),
  },
}));

describe('useWorktreeStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorktreeStore.setState({
      worktrees: [],
      activeWorktree: null,
      loading: false,
      error: null,
      currentSessionAnchor: null,
      createModalOpen: false,
    });
  });

  it('fetches worktrees and sets current active worktree', async () => {
    const list = [
      {
        path: '/repo/main',
        branch: 'main',
        head_commit: '111111',
        is_current: false,
        is_bare: false,
        is_dirty: false,
        is_locked: false,
        lock_reason: null,
      },
      {
        path: '/repo/.worktrees/dev',
        branch: 'dev',
        head_commit: '222222',
        is_current: true,
        is_bare: false,
        is_dirty: false,
        is_locked: false,
        lock_reason: null,
      },
    ];
    vi.mocked(worktreeService.listWorktrees).mockResolvedValueOnce(list);

    await useWorktreeStore.getState().fetchWorktrees();

    expect(useWorktreeStore.getState().worktrees).toHaveLength(2);
    expect(useWorktreeStore.getState().activeWorktree?.branch).toBe('dev');
  });

  it('switches active worktree and updates session anchor status', async () => {
    const initialList = [
      {
        path: '/repo/main',
        branch: 'main',
        head_commit: '111111',
        is_current: true,
        is_bare: false,
        is_dirty: false,
        is_locked: false,
        lock_reason: null,
      },
      {
        path: '/repo/.worktrees/dev',
        branch: 'dev',
        head_commit: '222222',
        is_current: false,
        is_bare: false,
        is_dirty: false,
        is_locked: false,
        lock_reason: null,
      },
    ];
    useWorktreeStore.setState({
      worktrees: initialList,
      activeWorktree: initialList[0],
      currentSessionAnchor: {
        session_id: 's-1',
        project_root: '/repo',
        worktree_path: '/repo/.worktrees/dev',
        checkout_ref: 'dev',
        is_anchored: false,
        active_worktree_path: '/repo/main',
        touched_files: [],
        created_at: '2026-09-02T10:00:00Z',
      },
    });

    vi.mocked(worktreeService.switchWorktree).mockResolvedValueOnce({
      ...initialList[1],
      is_current: true,
    });

    await useWorktreeStore.getState().switchActiveWorktree('/repo/.worktrees/dev');

    const state = useWorktreeStore.getState();
    expect(state.activeWorktree?.path).toBe('/repo/.worktrees/dev');
    expect(state.currentSessionAnchor?.is_anchored).toBe(true);
  });

  it('creates new worktree and sets it active', async () => {
    const newWt = {
      path: '/repo/.worktrees/feat-test',
      branch: 'feat-test',
      head_commit: 'HEAD',
      is_current: true,
      is_bare: false,
      is_dirty: false,
      is_locked: false,
      lock_reason: null,
    };
    vi.mocked(worktreeService.createWorktree).mockResolvedValueOnce(newWt);

    const created = await useWorktreeStore.getState().createNewWorktree({ branch: 'feat-test' });

    expect(created.branch).toBe('feat-test');
    expect(useWorktreeStore.getState().activeWorktree?.branch).toBe('feat-test');
    expect(useWorktreeStore.getState().createModalOpen).toBe(false);
  });

  it('checks session anchor and syncs worktree to session anchor', async () => {
    const anchor = {
      session_id: 's-99',
      project_root: '/repo',
      worktree_path: '/repo/.worktrees/anchored-branch',
      checkout_ref: 'anchored-branch',
      is_anchored: false,
      active_worktree_path: '/repo/main',
      touched_files: [],
      created_at: '2026-09-02T10:00:00Z',
    };
    vi.mocked(worktreeService.getSessionCheckoutAnchor).mockResolvedValueOnce(anchor);
    vi.mocked(worktreeService.switchWorktree).mockResolvedValueOnce({
      path: '/repo/.worktrees/anchored-branch',
      branch: 'anchored-branch',
      head_commit: 'HEAD',
      is_current: true,
      is_bare: false,
      is_dirty: false,
      is_locked: false,
      lock_reason: null,
    });

    await useWorktreeStore.getState().checkSessionAnchor('s-99');
    expect(useWorktreeStore.getState().currentSessionAnchor?.session_id).toBe('s-99');

    await useWorktreeStore.getState().syncSessionToAnchor('s-99');
    expect(worktreeService.switchWorktree).toHaveBeenCalledWith(
      '/repo/.worktrees/anchored-branch',
      undefined,
    );
  });
});
