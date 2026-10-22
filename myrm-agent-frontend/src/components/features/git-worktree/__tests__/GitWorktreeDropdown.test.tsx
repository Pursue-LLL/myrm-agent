import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { GitWorktreeDropdown } from '../GitWorktreeDropdown';
import { useWorktreeStore } from '../useWorktreeStore';

const mockTranslations = (key: string) => {
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

describe('GitWorktreeDropdown', () => {
  const dummyWorktrees = [
    {
      path: '/workspace',
      branch: 'main',
      head_commit: 'abc1234',
      is_current: true,
      is_bare: false,
      is_dirty: false,
      is_locked: false,
      lock_reason: null,
    },
    {
      path: '/workspace/.worktrees/feature-auth',
      branch: 'feature-auth',
      head_commit: 'def5678',
      is_current: false,
      is_bare: false,
      is_dirty: true,
      is_locked: false,
      lock_reason: null,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    useWorktreeStore.setState({
      worktrees: dummyWorktrees,
      activeWorktree: dummyWorktrees[0],
      loading: false,
      error: null,
      currentSessionAnchor: null,
      createModalOpen: false,
      fetchWorktrees: vi.fn(),
      switchActiveWorktree: vi.fn(),
      createNewWorktree: vi.fn(),
      removeWorktree: vi.fn(),
      checkSessionAnchor: vi.fn(),
      syncSessionToAnchor: vi.fn(),
      setCreateModalOpen: (open) => useWorktreeStore.setState({ createModalOpen: open }),
      resetError: vi.fn(),
    });
  });

  it('renders active worktree branch and head commit', () => {
    render(<GitWorktreeDropdown />);
    expect(screen.getByText('main')).toBeInTheDocument();
    expect(screen.getByText('abc1234')).toBeInTheDocument();
  });

  it('toggles dropdown popover on trigger button click', async () => {
    render(<GitWorktreeDropdown />);
    const trigger = screen.getByRole('button', { name: /main/i });

    fireEvent.click(trigger);
    expect(screen.getByTestId('git-worktree-popover')).toBeInTheDocument();
    expect(screen.getByText('feature-auth')).toBeInTheDocument();

    fireEvent.click(trigger);
    expect(screen.queryByTestId('git-worktree-popover')).not.toBeInTheDocument();
  });

  it('triggers switchActiveWorktree when selecting another worktree', async () => {
    const switchMock = vi.fn().mockResolvedValue(undefined);
    useWorktreeStore.setState({ switchActiveWorktree: switchMock });

    render(<GitWorktreeDropdown />);
    const trigger = screen.getByRole('button', { name: /main/i });
    fireEvent.click(trigger);

    const option = screen.getByTestId('worktree-option-feature-auth');
    fireEvent.click(option);

    expect(switchMock).toHaveBeenCalledWith(
      '/workspace/.worktrees/feature-auth',
      undefined,
    );
  });

  it('opens create modal and handles worktree creation submission', async () => {
    const createMock = vi.fn().mockResolvedValue({
      path: '/workspace/.worktrees/feature-new',
      branch: 'feature-new',
      head_commit: 'HEAD',
      is_current: true,
      is_bare: false,
      is_dirty: false,
      is_locked: false,
      lock_reason: null,
    });
    useWorktreeStore.setState({ createNewWorktree: createMock });

    render(<GitWorktreeDropdown />);
    const trigger = screen.getByRole('button', { name: /main/i });
    fireEvent.click(trigger);

    const newBtn = screen.getByRole('button', { name: /newWorktree/i });
    fireEvent.click(newBtn);

    expect(useWorktreeStore.getState().createModalOpen).toBe(true);

    const branchInput = screen.getByLabelText(/branchName/i);
    fireEvent.change(branchInput, { target: { value: 'feature-new' } });

    const submitBtn = screen.getByRole('button', { name: /confirm/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith({
        branch: 'feature-new',
        base_ref: 'HEAD',
        repo_path: undefined,
      });
    });
  });
});
