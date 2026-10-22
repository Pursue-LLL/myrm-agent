/**
 * [INPUT]
 * - @testing-library/react (POS: React Component Testing)
 * - @/components/features/chat-window/workspace-breadcrumb/WorkspaceBreadcrumbBar
 * - @/components/features/chat-window/workspace-breadcrumb/useWorkspaceBreadcrumbStore
 * - @/components/features/chat-window/workspace-breadcrumb/workspaceBreadcrumbTypes
 *
 * [OUTPUT]
 * - End-to-end integration test suite verifying multi-session path dispatching and desktop event bridging.
 */

import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { WorkspaceBreadcrumbBar } from '../WorkspaceBreadcrumbBar';
import { useWorkspaceBreadcrumbStore } from '../useWorkspaceBreadcrumbStore';
import type { WorkspaceRevealEventPayload } from '../workspaceBreadcrumbTypes';

describe('WorkspaceBreadcrumb Integration Workflow', () => {
  const capturedEvents: WorkspaceRevealEventPayload[] = [];

  const handleRevealEvent = (e: Event) => {
    const custom = e as CustomEvent<WorkspaceRevealEventPayload>;
    if (custom.detail) {
      capturedEvents.push(custom.detail);
    }
  };

  beforeEach(() => {
    capturedEvents.length = 0;
    useWorkspaceBreadcrumbStore.getState().resetStore();
    window.addEventListener('myrm:workspace-reveal', handleRevealEvent);
  });

  afterEach(() => {
    window.removeEventListener('myrm:workspace-reveal', handleRevealEvent);
    vi.restoreAllMocks();
  });

  it('should synchronize across active chat session switches and broadcast desktop bridge events', async () => {
    const store = useWorkspaceBreadcrumbStore.getState();

    // 配置两个不同会话的物理路径
    store.setWorkspacePath('session_alpha', '/Users/developer/projects/alpha-core');
    store.setWorkspacePath('session_beta', '/sandbox/isolated-cluster/beta-worker');

    const { rerender } = render(<WorkspaceBreadcrumbBar chatId="session_alpha" />);

    // 验证 Session Alpha 状态
    expect(screen.getByTestId('workspace-badge')).toHaveTextContent('物理工作区');
    expect(screen.getByText('alpha-core')).toBeInTheDocument();

    // 触发 Finder 定位
    fireEvent.click(screen.getByTestId('btn-reveal-finder'));
    expect(capturedEvents).toHaveLength(1);
    expect(capturedEvents[0].action).toBe('finder');
    expect(capturedEvents[0].path).toBe('/Users/developer/projects/alpha-core');

    // 切换至 Session Beta
    rerender(<WorkspaceBreadcrumbBar chatId="session_beta" />);

    // 验证 Session Beta 状态
    expect(screen.getByTestId('workspace-badge')).toHaveTextContent('沙箱隔离');
    expect(screen.getByText('beta-worker')).toBeInTheDocument();

    // 触发 Terminal 开启
    fireEvent.click(screen.getByTestId('btn-reveal-terminal'));
    expect(capturedEvents).toHaveLength(2);
    expect(capturedEvents[1].action).toBe('terminal');
    expect(capturedEvents[1].path).toBe('/sandbox/isolated-cluster/beta-worker');
  });

  it('should react dynamically when store updates current workspace path in real-time', () => {
    const store = useWorkspaceBreadcrumbStore.getState();
    store.setDefaultPath('/Users/dev/initial-repo');

    render(<WorkspaceBreadcrumbBar />);
    expect(screen.getByText('initial-repo')).toBeInTheDocument();

    act(() => {
      useWorkspaceBreadcrumbStore.getState().setDefaultPath('/Users/dev/updated-monorepo');
    });

    expect(screen.getByText('updated-monorepo')).toBeInTheDocument();
  });
});
