import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DockableWorkbenchContainer } from '../DockableWorkbenchContainer';
import { useDockableWorkbenchStore } from '../useDockableWorkbenchStore';

describe('DockableWorkbenchContainer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDockableWorkbenchStore.getState().resetStore();
    useDockableWorkbenchStore.setState({
      activePanelId: 'changes',
      dockPosition: 'right',
      isCollapsed: false,
      bootstrapData: {
        sessionId: 'sess-test-1',
        sessionTitle: '架构重构长会话',
        activeAgentName: '系统架构师',
        sandboxChanges: [],
        eventBaselineEpoch: 1,
        initialMessagesCount: 15,
        cachedAt: '2026-10-15T18:00:00Z',
      },
    });
  });

  it('容器应正确渲染中央主会话区、Bootstrap 头部元数据与子元素', () => {
    render(
      <DockableWorkbenchContainer>
        <div data-testid="chat-stream-child">对话流内容区</div>
      </DockableWorkbenchContainer>
    );

    expect(screen.getByTestId('dockable-workbench-container')).toBeInTheDocument();
    expect(screen.getByText('架构重构长会话')).toBeInTheDocument();
    expect(screen.getByText('(系统架构师)')).toBeInTheDocument();
    expect(screen.getByText('基线代次: E1')).toBeInTheDocument();
    expect(screen.getByTestId('chat-stream-child')).toBeInTheDocument();
  });

  it('点击面板标签页能切换不同辅助观察面板', () => {
    render(<DockableWorkbenchContainer />);

    const fileTab = screen.getByRole('button', { name: /文件速览/i });
    fireEvent.click(fileTab);
    expect(useDockableWorkbenchStore.getState().activePanelId).toBe('file_preview');
    expect(screen.getByText(/只读文件速览/)).toBeInTheDocument();

    const browserTab = screen.getByRole('button', { name: /浏览器/i });
    fireEvent.click(browserTab);
    expect(useDockableWorkbenchStore.getState().activePanelId).toBe('live_browser');
    expect(screen.getByText(/画中画自动化视窗/)).toBeInTheDocument();

    const termTab = screen.getByRole('button', { name: /终端/i });
    fireEvent.click(termTab);
    expect(useDockableWorkbenchStore.getState().activePanelId).toBe('terminal');
    expect(screen.getByText(/全屏 Web 终端/)).toBeInTheDocument();
  });

  it('点击切换停靠位置按钮能更改 dockPosition 为 bottom', () => {
    render(<DockableWorkbenchContainer />);

    const posBtn = screen.getByRole('button', { name: '切换停靠位置' });
    fireEvent.click(posBtn);

    expect(useDockableWorkbenchStore.getState().dockPosition).toBe('bottom');
  });

  it('点击折叠与关闭按钮能正确控制面板生命周期', () => {
    render(<DockableWorkbenchContainer />);

    const collapseBtn = screen.getByRole('button', { name: '折叠或展开面板' });
    fireEvent.click(collapseBtn);
    expect(useDockableWorkbenchStore.getState().isCollapsed).toBe(true);

    const closeBtn = screen.getByRole('button', { name: '关闭面板' });
    fireEvent.click(closeBtn);
    expect(useDockableWorkbenchStore.getState().dockPosition).toBe('closed');
  });
});
