/**
 * [INPUT]
 * BoundaryHandshakeCard, ProjectSwitchHandshakeResponse
 * [OUTPUT]
 * Unit tests covering boundary handshake safety card, risk badges, and switch triggers.
 * [POS]
 * src/components/features/workspace-boundary/__tests__/BoundaryHandshakeCard.test.tsx
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { BoundaryHandshakeCard } from '../BoundaryHandshakeCard';
import { ProjectSwitchHandshakeResponse } from '../workspaceBoundaryTypes';

describe('BoundaryHandshakeCard', () => {
  const safeHandshake: ProjectSwitchHandshakeResponse = {
    target_project_id: 'proj-omega',
    target_path: '/Users/dev/repos/proj-omega',
    path_exists: true,
    is_git_repo: true,
    git_branch: 'feat/next-gen',
    git_worktree: null,
    git_uncommitted_changes: 0,
    risk_level: 'safe',
    warnings: [],
    can_switch: true,
    handshake_token: 'valid-token-12345',
  };

  it('renders safe handshake details and enables switch action', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();

    render(
      <BoundaryHandshakeCard
        handshake={safeHandshake}
        onConfirmSwitch={onConfirm}
        onCancelSwitch={onCancel}
      />
    );

    expect(screen.getByTestId('boundary-handshake-card')).toBeDefined();
    expect(screen.getByTestId('risk-badge-safe')).toBeDefined();
    expect(screen.getByText('Safe Handshake')).toBeDefined();
    expect(screen.getByText('/Users/dev/repos/proj-omega')).toBeDefined();
    expect(screen.getByText('feat/next-gen')).toBeDefined();
    expect(screen.getByText('Working tree clean')).toBeDefined();

    const confirmBtn = screen.getByTestId('handshake-confirm-btn');
    expect(confirmBtn.hasAttribute('disabled')).toBe(false);

    fireEvent.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledWith('valid-token-12345');

    const cancelBtn = screen.getByTestId('handshake-cancel-btn');
    fireEvent.click(cancelBtn);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('renders warning badge and uncommitted changes when dirty files exist', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const warningHandshake: ProjectSwitchHandshakeResponse = {
      ...safeHandshake,
      git_uncommitted_changes: 3,
      risk_level: 'warning',
      warnings: ['Target workspace has 3 uncommitted changes. Beware of uncommitted edits.'],
    };

    render(
      <BoundaryHandshakeCard
        handshake={warningHandshake}
        onConfirmSwitch={onConfirm}
        onCancelSwitch={onCancel}
      />
    );

    expect(screen.getByTestId('risk-badge-warning')).toBeDefined();
    expect(screen.getByTestId('target-dirty-changes')).toBeDefined();
    expect(screen.getByText('3 uncommitted files')).toBeDefined();
    expect(screen.getByTestId('handshake-warnings')).toBeDefined();
    expect(screen.getByText(/Target workspace has 3 uncommitted changes/)).toBeDefined();
  });

  it('renders blocked badge and disables confirm button when can_switch is false', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const blockedHandshake: ProjectSwitchHandshakeResponse = {
      target_project_id: 'proj-404',
      target_path: '/Users/dev/repos/non_existent',
      path_exists: false,
      is_git_repo: false,
      git_branch: '',
      git_worktree: null,
      git_uncommitted_changes: 0,
      risk_level: 'blocked',
      warnings: ["Target workspace path '/Users/dev/repos/non_existent' does not exist on disk."],
      can_switch: false,
      handshake_token: '',
    };

    render(
      <BoundaryHandshakeCard
        handshake={blockedHandshake}
        onConfirmSwitch={onConfirm}
        onCancelSwitch={onCancel}
      />
    );

    expect(screen.getByTestId('risk-badge-blocked')).toBeDefined();
    expect(screen.getByText('Blocked')).toBeDefined();
    expect(screen.getByText(/does not exist on disk/)).toBeDefined();

    const confirmBtn = screen.getByTestId('handshake-confirm-btn');
    expect(confirmBtn.hasAttribute('disabled')).toBe(true);

    fireEvent.click(confirmBtn);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
