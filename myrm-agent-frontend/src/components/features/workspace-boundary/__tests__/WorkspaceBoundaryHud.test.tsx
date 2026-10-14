/**
 * [INPUT]
 * WorkspaceBoundaryHud, ThreeCurrentsBoundary
 * [OUTPUT]
 * Comprehensive unit tests for WorkspaceBoundaryHud component.
 * [POS]
 * src/components/features/workspace-boundary/__tests__/WorkspaceBoundaryHud.test.tsx
 */

import React, { act } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { WorkspaceBoundaryHud } from '../WorkspaceBoundaryHud';
import { ThreeCurrentsBoundary } from '../workspaceBoundaryTypes';

describe('WorkspaceBoundaryHud', () => {
  const mockBoundary: ThreeCurrentsBoundary = {
    session_id: 'sess-test-01',
    project_id: 'proj-myrm',
    project_name: 'Myrmidon',
    session_goal: 'Implement HUD Boundary',
    cwd: '/Users/dev/myrm-agent',
    repo_name: 'myrm-agent',
    git_branch: 'main',
    git_worktree: 'feat-hud',
    git_is_clean: true,
    git_uncommitted_changes: 0,
    execution_host_type: 'local_host',
    execution_host_label: '💻 Local Mac',
    execution_host_id: 'host-darwin-01',
    inspected_at: 1760000000,
  };

  it('renders all three currents capsules with clean git status', () => {
    render(<WorkspaceBoundaryHud boundary={mockBoundary} />);

    expect(screen.getByTestId('workspace-boundary-hud')).toBeDefined();
    expect(screen.getByTestId('hud-capsule-session')).toBeDefined();
    expect(screen.getByText(/Implement HUD Boundary/)).toBeDefined();

    expect(screen.getByTestId('hud-capsule-git')).toBeDefined();
    expect(screen.getByText(/main @ feat-hud/)).toBeDefined();
    expect(screen.getByTestId('git-status-clean')).toBeDefined();

    expect(screen.getByTestId('hud-capsule-host')).toBeDefined();
    expect(screen.getByText('💻 Local Mac')).toBeDefined();
  });

  it('renders dirty git status with uncommitted files count badge', () => {
    const dirtyBoundary: ThreeCurrentsBoundary = {
      ...mockBoundary,
      git_is_clean: false,
      git_uncommitted_changes: 5,
    };

    render(<WorkspaceBoundaryHud boundary={dirtyBoundary} />);

    expect(screen.getByTestId('git-status-dirty')).toBeDefined();
    expect(screen.getByText('5')).toBeDefined();
  });

  it('renders cloud sandbox host label and icon properly', () => {
    const cloudBoundary: ThreeCurrentsBoundary = {
      ...mockBoundary,
      execution_host_type: 'cloud_sandbox',
      execution_host_label: '☁️ Cloud Sandbox #sbx-99',
    };

    render(<WorkspaceBoundaryHud boundary={cloudBoundary} />);

    expect(screen.getByText('☁️ Cloud Sandbox #sbx-99')).toBeDefined();
  });

  it('toggles expansion panel showing full CWD and execution metadata', () => {
    const onSwitchProject = vi.fn();
    render(
      <WorkspaceBoundaryHud
        boundary={mockBoundary}
        onRequestSwitchProject={onSwitchProject}
      />
    );

    expect(screen.queryByTestId('hud-expanded-panel')).toBeNull();

    const expandBtn = screen.getByTestId('hud-expand-toggle-btn');
    fireEvent.click(expandBtn);

    expect(screen.getByTestId('hud-expanded-panel')).toBeDefined();
    expect(screen.getByText('/Users/dev/myrm-agent')).toBeDefined();
    expect(screen.getByText('sess-test-01')).toBeDefined();

    const switchBtn = screen.getByTestId('hud-switch-project-btn');
    fireEvent.click(switchBtn);
    expect(onSwitchProject).toHaveBeenCalledTimes(1);
  });

  it('handles refresh button and worktree matrix button clicks', async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const onOpenMatrix = vi.fn();

    render(
      <WorkspaceBoundaryHud
        boundary={mockBoundary}
        onRefresh={onRefresh}
        onOpenWorktreeMatrix={onOpenMatrix}
      />
    );

    const refreshBtn = screen.getByTestId('hud-refresh-btn');
    await act(async () => {
      fireEvent.click(refreshBtn);
    });
    expect(onRefresh).toHaveBeenCalledTimes(1);

    const matrixBtn = screen.getByTestId('hud-worktree-matrix-btn');
    fireEvent.click(matrixBtn);
    expect(onOpenMatrix).toHaveBeenCalledTimes(1);
  });
});
