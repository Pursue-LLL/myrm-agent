/**
 * [INPUT]
 * WorktreeMatrixNavigator, MultiRepoWorktreeEntry
 * [OUTPUT]
 * Comprehensive unit tests for WorktreeMatrixNavigator component.
 * [POS]
 * src/components/features/workspace-boundary/__tests__/WorktreeMatrixNavigator.test.tsx
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { WorktreeMatrixNavigator } from '../WorktreeMatrixNavigator';
import { MultiRepoWorktreeEntry } from '../workspaceBoundaryTypes';

describe('WorktreeMatrixNavigator', () => {
  const mockEntries: MultiRepoWorktreeEntry[] = [
    {
      repo: 'myrm-agent',
      worktree: null,
      branch: 'main',
      path: '/Users/dev/repos/myrm-agent',
      is_active: true,
    },
    {
      repo: 'myrm-agent',
      worktree: 'feat-hud',
      branch: 'feat/boundary-hud',
      path: '/Users/dev/repos/myrm-agent-hud',
      is_active: false,
    },
    {
      repo: 'myrm-control-plane',
      worktree: null,
      branch: 'master',
      path: '/Users/dev/repos/myrm-control-plane',
      is_active: false,
    },
  ];

  it('renders list of worktrees with active badge and branch labels', () => {
    const onSelect = vi.fn();
    render(<WorktreeMatrixNavigator entries={mockEntries} onSelectWorktree={onSelect} />);

    expect(screen.getByTestId('worktree-matrix-navigator')).toBeDefined();
    expect(screen.getByText('Multi-Repo & Git Worktree Matrix')).toBeDefined();
    expect(screen.getByText('main')).toBeDefined();
    expect(screen.getByText('feat/boundary-hud')).toBeDefined();
    expect(screen.getByText('master')).toBeDefined();

    expect(screen.getByTestId('worktree-active-badge')).toBeDefined();
    expect(screen.getByText('Active')).toBeDefined();
  });

  it('triggers onSelectWorktree when switch button on inactive worktree is clicked', () => {
    const onSelect = vi.fn();
    render(<WorktreeMatrixNavigator entries={mockEntries} onSelectWorktree={onSelect} />);

    const switchBtn = screen.getByTestId('switch-worktree-btn-1');
    fireEvent.click(switchBtn);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(mockEntries[1]);
  });

  it('renders empty state when no worktree entries exist', () => {
    const onSelect = vi.fn();
    render(<WorktreeMatrixNavigator entries={[]} onSelectWorktree={onSelect} />);

    expect(screen.getByTestId('worktree-empty-state')).toBeDefined();
    expect(
      screen.getByText('No linked Git worktrees found for current workspace.')
    ).toBeDefined();
  });

  it('triggers onClose when close button is clicked', () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();

    render(
      <WorktreeMatrixNavigator
        entries={mockEntries}
        onSelectWorktree={onSelect}
        onClose={onClose}
      />
    );

    const closeBtn = screen.getByTestId('worktree-matrix-close-btn');
    fireEvent.click(closeBtn);

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
