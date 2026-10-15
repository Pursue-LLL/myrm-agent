import React, { act } from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CommandCenterModal } from '../CommandCenterModal';
import { CommandCenterHeaderTrigger } from '../CommandCenterHeaderTrigger';
import { useCommandCenterStore } from '../useCommandCenterStore';

describe('CommandCenterModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCommandCenterStore.getState().resetStore();
  });

  it('初始状态下浮层不应渲染在 DOM 中', () => {
    render(<CommandCenterModal />);
    expect(screen.queryByTestId('command-center-modal')).not.toBeInTheDocument();
  });

  it('调用 openModal 或点击 HeaderTrigger 应渲染浮层并默认展示 Sessions Tab', () => {
    render(
      <>
        <CommandCenterHeaderTrigger />
        <CommandCenterModal />
      </>
    );

    const triggerBtn = screen.getByTestId('command-center-header-trigger');
    fireEvent.click(triggerBtn);

    expect(screen.getByTestId('command-center-modal')).toBeInTheDocument();
    expect(screen.getByText('COMMAND CENTER')).toBeInTheDocument();
    expect(screen.getByTestId('command-center-sessions-tab')).toBeInTheDocument();
  });

  it('点击不同 Tab 按钮应平滑切换内容面板', () => {
    useCommandCenterStore.getState().openModal('sessions');
    render(<CommandCenterModal />);

    // 切换到网关体态与日志
    const systemTabBtn = screen.getByRole('button', { name: /网关体态与日志/i });
    fireEvent.click(systemTabBtn);
    expect(screen.getByTestId('command-center-system-tab')).toBeInTheDocument();

    // 切换到用量与资产排行
    const usageTabBtn = screen.getByRole('button', { name: /用量与资产排行/i });
    fireEvent.click(usageTabBtn);
    expect(screen.getByTestId('command-center-usage-tab')).toBeInTheDocument();

    // 切换到维护与排障中心
    const maintenanceTabBtn = screen.getByRole('button', { name: /维护与排障中心/i });
    fireEvent.click(maintenanceTabBtn);
    expect(screen.getByTestId('command-center-maintenance-tab')).toBeInTheDocument();
  });

  it('点击关闭按钮或按 Escape 键能关闭浮层', () => {
    useCommandCenterStore.getState().openModal('sessions');
    render(<CommandCenterModal />);

    expect(screen.getByTestId('command-center-modal')).toBeInTheDocument();

    const closeBtn = screen.getByRole('button', { name: /关闭/i });
    fireEvent.click(closeBtn);

    expect(screen.queryByTestId('command-center-modal')).not.toBeInTheDocument();

    // 再次打开并通过键盘 Escape 关闭
    act(() => {
      useCommandCenterStore.getState().openModal('sessions');
    });
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(useCommandCenterStore.getState().isOpen).toBe(false);
  });
});
