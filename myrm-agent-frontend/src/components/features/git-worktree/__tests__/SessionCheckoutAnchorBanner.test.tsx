import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { SessionCheckoutAnchorBanner } from '../SessionCheckoutAnchorBanner';
import { useWorktreeStore } from '../useWorktreeStore';

const mockTranslations = (key: string, values?: Record<string, unknown>) => {
  if (key === 'syncedHint') {
    return `Workspace anchored to ${values?.branch}`;
  }
  if (key === 'mismatchDesc') {
    return `Created on ${values?.sessionBranch}, active is ${values?.activeBranch}`;
  }
  if (key === 'touchedFiles') {
    return 'files';
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function mockShowModal(this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function mockClose(this: HTMLDialogElement) {
    this.open = false;
  });
});

describe('SessionCheckoutAnchorBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders green synced banner when session is anchored to active worktree', () => {
    useWorktreeStore.setState({
      activeWorktree: {
        path: '/workspace',
        branch: 'main',
        head_commit: '123456',
        is_current: true,
        is_bare: false,
        is_dirty: false,
        is_locked: false,
        lock_reason: null,
      },
      currentSessionAnchor: {
        session_id: 'sess-sync',
        project_root: '/workspace',
        worktree_path: '/workspace',
        checkout_ref: 'main',
        is_anchored: true,
        active_worktree_path: '/workspace',
        touched_files: [
          { file_path: 'src/app.ts', change_type: 'modified', touched_at: '2026-09-02T10:00:00Z' },
        ],
        created_at: '2026-09-02T10:00:00Z',
      },
      checkSessionAnchor: vi.fn(),
      syncSessionToAnchor: vi.fn(),
    });

    render(<SessionCheckoutAnchorBanner sessionId="sess-sync" />);

    expect(screen.getByTestId('session-checkout-anchor-synced')).toBeInTheDocument();
    expect(screen.getByText('Workspace anchored to main')).toBeInTheDocument();
    expect(screen.getByText(/1 files/i)).toBeInTheDocument();
  });

  it('renders warning banner and triggers sync when unanchored', async () => {
    const syncMock = vi.fn().mockResolvedValue(undefined);
    useWorktreeStore.setState({
      activeWorktree: {
        path: '/workspace',
        branch: 'main',
        head_commit: '123456',
        is_current: true,
        is_bare: false,
        is_dirty: false,
        is_locked: false,
        lock_reason: null,
      },
      currentSessionAnchor: {
        session_id: 'sess-drift',
        project_root: '/workspace',
        worktree_path: '/workspace/.worktrees/feature-x',
        checkout_ref: 'feature-x',
        is_anchored: false,
        active_worktree_path: '/workspace',
        touched_files: [],
        created_at: '2026-09-02T10:00:00Z',
      },
      checkSessionAnchor: vi.fn(),
      syncSessionToAnchor: syncMock,
    });

    render(<SessionCheckoutAnchorBanner sessionId="sess-drift" />);

    expect(screen.getByTestId('session-checkout-anchor-unanchored')).toBeInTheDocument();
    expect(screen.getByText('Created on feature-x, active is main')).toBeInTheDocument();

    const switchBtn = screen.getByRole('button', { name: /switchBack/i });
    fireEvent.click(switchBtn);

    await waitFor(() => {
      expect(syncMock).toHaveBeenCalledWith('sess-drift');
    });
  });

  it('opens touched files popover when clicking touched files badge', () => {
    useWorktreeStore.setState({
      activeWorktree: {
        path: '/workspace',
        branch: 'main',
        head_commit: '123456',
        is_current: true,
        is_bare: false,
        is_dirty: false,
        is_locked: false,
        lock_reason: null,
      },
      currentSessionAnchor: {
        session_id: 'sess-popover',
        project_root: '/workspace',
        worktree_path: '/workspace',
        checkout_ref: 'main',
        is_anchored: true,
        active_worktree_path: '/workspace',
        touched_files: [
          { file_path: 'src/routes.ts', change_type: 'created', touched_at: '2026-09-02T10:00:00Z' },
        ],
        created_at: '2026-09-02T10:00:00Z',
      },
      checkSessionAnchor: vi.fn(),
      syncSessionToAnchor: vi.fn(),
    });

    render(<SessionCheckoutAnchorBanner sessionId="sess-popover" />);

    const badge = screen.getByRole('button', { name: /1 files/i });
    fireEvent.click(badge);

    expect(screen.getByTestId('session-touched-files-dialog')).toBeInTheDocument();
    expect(screen.getByText('src/routes.ts')).toBeInTheDocument();
  });
});
