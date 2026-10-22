/**
 * [INPUT]
 * - @testing-library/react (POS: React Component Testing)
 * - @/components/features/chat-window/session-branch-archive/SessionRuleAnchorHeader
 * - @/components/features/chat-window/session-branch-archive/SessionBranchArchiveModal
 * - @/components/features/chat-window/session-branch-archive/useSessionBranchArchiveStore
 * - @/components/features/chat-window/session-branch-archive/sessionBranchArchiveTypes
 *
 * [OUTPUT]
 * - End-to-end integration test suite verifying archive /new reset workflows, branch trees, and modal lifecycle.
 */

import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { SessionRuleAnchorHeader } from '../SessionRuleAnchorHeader';
import { SessionBranchArchiveModal } from '../SessionBranchArchiveModal';
import { useSessionBranchArchiveStore } from '../useSessionBranchArchiveStore';
import type { SessionBranchEventPayload } from '../sessionBranchArchiveTypes';

describe('SessionBranchArchive Integration Workflow', () => {
  const capturedEvents: SessionBranchEventPayload[] = [];

  const handleBranchEvent = (e: Event) => {
    const custom = e as CustomEvent<SessionBranchEventPayload>;
    if (custom.detail) {
      capturedEvents.push(custom.detail);
    }
  };

  beforeEach(() => {
    capturedEvents.length = 0;
    useSessionBranchArchiveStore.getState().resetStore();
    window.addEventListener('myrm:session-branch-archived', handleBranchEvent);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    window.removeEventListener('myrm:session-branch-archived', handleBranchEvent);
    vi.restoreAllMocks();
  });

  it('should complete archive-and-reset workflow, broadcast events, and display snapshots in modal', () => {
    const initialSessionId = 'sess-initial-task';
    useSessionBranchArchiveStore.getState().setCurrentSessionId(initialSessionId);
    useSessionBranchArchiveStore.getState().setCurrentRuleHash('rule-v1');

    render(
      <div>
        <SessionRuleAnchorHeader
          currentMessageCount={35}
          currentTokenCount={48000}
        />
        <SessionBranchArchiveModal />
      </div>,
    );

    // 初始状态：无快照
    expect(screen.getByText('归档快照 (0)')).toBeInTheDocument();
    expect(screen.queryByTestId('session-branch-archive-modal')).not.toBeInTheDocument();

    // 点击顶栏【归档并重启 (/new)】
    const archiveBtn = screen.getByTestId('btn-archive-reset');
    fireEvent.click(archiveBtn);

    // 验证事件广播
    expect(capturedEvents).toHaveLength(1);
    expect(capturedEvents[0].action).toBe('archive_and_reset');
    expect(capturedEvents[0].sessionId).not.toBe(initialSessionId);

    // 验证快照计数更新
    expect(screen.getByText('归档快照 (1)')).toBeInTheDocument();

    // 点击唤出归档看板弹窗
    fireEvent.click(screen.getByTestId('btn-view-snapshots'));
    expect(screen.getByTestId('session-branch-archive-modal')).toBeInTheDocument();
    expect(screen.getByText('会话分支归档与规矩恒常重置看板')).toBeInTheDocument();

    // 验证快照条目
    const storeState = useSessionBranchArchiveStore.getState();
    const snapshotId = storeState.snapshots[0].id;
    expect(screen.getByTestId(`snapshot-item-${snapshotId}`)).toBeInTheDocument();
    expect(screen.getByText('35 条消息')).toBeInTheDocument();
    expect(screen.getByText('48,000 tokens')).toBeInTheDocument();

    // 点击删除该快照
    const removeBtn = screen.getByTestId(`btn-remove-snapshot-${snapshotId}`);
    fireEvent.click(removeBtn);

    // 验证快照被清理，显示空状态提示
    expect(screen.getByTestId('snapshots-empty-hint')).toBeInTheDocument();

    // 关闭弹窗
    const closeBtn = screen.getByTestId('btn-close-modal');
    fireEvent.click(closeBtn);
    expect(screen.queryByTestId('session-branch-archive-modal')).not.toBeInTheDocument();
  });

  it('should support exploration branch forking and switching in modal', () => {
    render(
      <div>
        <SessionRuleAnchorHeader />
        <SessionBranchArchiveModal />
      </div>,
    );

    // 点击 /fork 派生分支
    fireEvent.click(screen.getByTestId('btn-fork-branch'));

    expect(capturedEvents).toHaveLength(1);
    expect(capturedEvents[0].action).toBe('fork_branch');

    // 打开看板弹窗查看分支树
    fireEvent.click(screen.getByTestId('btn-view-snapshots'));

    const branchRoot = useSessionBranchArchiveStore.getState().branchRoot;
    expect(branchRoot).not.toBeNull();
    if (branchRoot) {
      expect(screen.getByTestId(`branch-node-${branchRoot.id}`)).toBeInTheDocument();
    }

    // 在 store 中再次派生子分支并测试切换
    act(() => {
      useSessionBranchArchiveStore.getState().forkBranchFromMessage('msg-cp-2', '子分支探索');
    });

    const activeBranchId = useSessionBranchArchiveStore.getState().activeBranchId;
    if (activeBranchId) {
      const branchBtn = screen.getByTestId(`branch-node-${activeBranchId}`);
      expect(branchBtn).toBeInTheDocument();
    }
  });
});
