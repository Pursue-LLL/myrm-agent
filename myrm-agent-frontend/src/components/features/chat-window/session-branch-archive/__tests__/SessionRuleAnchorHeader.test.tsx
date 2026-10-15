/**
 * [INPUT]
 * - @testing-library/react (POS: React Component Testing)
 * - @/components/features/chat-window/session-branch-archive/SessionRuleAnchorHeader
 * - @/components/features/chat-window/session-branch-archive/useSessionBranchArchiveStore
 *
 * [OUTPUT]
 * - Component UI unit test suite for SessionRuleAnchorHeader rendering, /new actions, and /fork triggers.
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SessionRuleAnchorHeader } from '../SessionRuleAnchorHeader';
import { useSessionBranchArchiveStore } from '../useSessionBranchArchiveStore';

describe('SessionRuleAnchorHeader Component', () => {
  beforeEach(() => {
    useSessionBranchArchiveStore.getState().resetStore();
    vi.restoreAllMocks();
  });

  it('should render rule anchor badge and version hash', () => {
    useSessionBranchArchiveStore.getState().setCurrentRuleHash('rule-v1-hash');

    render(<SessionRuleAnchorHeader />);

    expect(screen.getByTestId('session-rule-anchor-header')).toBeInTheDocument();
    expect(screen.getByTestId('rule-anchor-badge')).toHaveTextContent('规矩放文件：项目规则已永久锚定');
    expect(screen.getByTestId('rule-version-hash')).toHaveTextContent('AGENTS.md #rule-v1-hash');
  });

  it('should trigger archive and reset on /new button click', () => {
    const onArchiveResetMock = vi.fn();

    render(
      <SessionRuleAnchorHeader
        onArchiveReset={onArchiveResetMock}
        currentMessageCount={25}
        currentTokenCount={32000}
      />,
    );

    const archiveResetBtn = screen.getByTestId('btn-archive-reset');
    fireEvent.click(archiveResetBtn);

    expect(onArchiveResetMock).toHaveBeenCalledTimes(1);

    const storeState = useSessionBranchArchiveStore.getState();
    expect(storeState.snapshots).toHaveLength(1);
    expect(storeState.snapshots[0].messageCount).toBe(25);
    expect(storeState.snapshots[0].totalTokens).toBe(32000);
  });

  it('should trigger branch fork on /fork button click', () => {
    const onForkBranchMock = vi.fn();

    render(<SessionRuleAnchorHeader onForkBranch={onForkBranchMock} />);

    const forkBtn = screen.getByTestId('btn-fork-branch');
    fireEvent.click(forkBtn);

    expect(onForkBranchMock).toHaveBeenCalledTimes(1);

    const storeState = useSessionBranchArchiveStore.getState();
    expect(storeState.branchRoot).not.toBeNull();
    expect(storeState.activeBranchId).not.toBeNull();
  });

  it('should open archive snapshots modal when view snapshots button is clicked', () => {
    render(<SessionRuleAnchorHeader />);

    const viewBtn = screen.getByTestId('btn-view-snapshots');
    expect(useSessionBranchArchiveStore.getState().isArchiveModalOpen).toBe(false);

    fireEvent.click(viewBtn);
    expect(useSessionBranchArchiveStore.getState().isArchiveModalOpen).toBe(true);
  });
});
