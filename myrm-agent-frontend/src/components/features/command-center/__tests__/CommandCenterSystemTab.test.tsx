import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CommandCenterSystemTab } from '../CommandCenterSystemTab';
import { useCommandCenterStore } from '../useCommandCenterStore';

describe('CommandCenterSystemTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCommandCenterStore.getState().resetStore();
  });

  it('应正确渲染网关健康指示卡、延迟与版本号', () => {
    render(<CommandCenterSystemTab />);

    expect(screen.getByTestId('command-center-system-tab')).toBeInTheDocument();
    expect(screen.getByText(/运行正常/)).toBeInTheDocument();
    expect(screen.getByText(/18 ms/)).toBeInTheDocument();
    expect(screen.getByText(/v2026.8.1-myrm/)).toBeInTheDocument();
    expect(screen.getByText(/local_python/)).toBeInTheDocument();
  });

  it('点击组件过滤按钮能筛选对应日志条目', () => {
    render(<CommandCenterSystemTab />);

    expect(screen.getByText(/Gateway HTTP\/WS router heartbeat/)).toBeInTheDocument();
    expect(screen.getByText(/Agent Arch-Master-4o dispatched tool/)).toBeInTheDocument();

    const gatewayFilterBtn = screen.getByRole('button', { name: /Gateway 网关/i });
    fireEvent.click(gatewayFilterBtn);

    expect(screen.getByText(/Gateway HTTP\/WS router heartbeat/)).toBeInTheDocument();
    expect(
      screen.queryByText(/Agent Arch-Master-4o dispatched tool/)
    ).not.toBeInTheDocument();
  });
});
