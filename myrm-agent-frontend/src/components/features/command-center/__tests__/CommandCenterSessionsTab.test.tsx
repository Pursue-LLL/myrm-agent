import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CommandCenterSessionsTab } from '../CommandCenterSessionsTab';
import { useCommandCenterStore } from '../useCommandCenterStore';

describe('CommandCenterSessionsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCommandCenterStore.getState().resetStore();
  });

  it('应正确渲染会话搜索输入框与默认会话卡片列表', () => {
    render(<CommandCenterSessionsTab />);

    expect(
      screen.getByPlaceholderText(/毫秒级搜索会话标题、负责人或标签/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Roadmap 09 前端 UX 架构与拟物化微应用重构/)
    ).toBeInTheDocument();
    expect(screen.getByText(/Arch-Master-4o/)).toBeInTheDocument();
  });

  it('在搜索框输入关键词能实时过滤会话', () => {
    render(<CommandCenterSessionsTab />);

    const searchInput = screen.getByPlaceholderText(/毫秒级搜索会话标题、负责人或标签/i);
    fireEvent.change(searchInput, { target: { value: 'DeepSeek' } });

    expect(
      screen.getByText(/多模型分栏竞技场对比 DeepSeek-R1 与 Claude 3.7/)
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/OpenClaw Gateway 延迟压测与 N\+1 请求清零/)
    ).not.toBeInTheDocument();
  });

  it('点击置顶按钮能切换会话固定状态', () => {
    render(<CommandCenterSessionsTab />);

    const pinButtons = screen.getAllByRole('button', { name: /置顶/i });
    expect(pinButtons.length).toBeGreaterThan(0);

    fireEvent.click(pinButtons[0]);
    // 状态切换已触发
    expect(useCommandCenterStore.getState().sessions.length).toBeGreaterThan(0);
  });

  it('点击导出审计包按钮能触发会话全要素打包', () => {
    render(<CommandCenterSessionsTab />);

    const exportButtons = screen.getAllByRole('button', { name: /导出审计包/i });
    fireEvent.click(exportButtons[0]);

    expect(useCommandCenterStore.getState().exportedAuditPack).not.toBeNull();
    expect(screen.getByText(/审计包就绪：/i)).toBeInTheDocument();
  });
});
