import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import useChatStore from '@/store/useChatStore';
import { useLaneSemanticStore } from '../useLaneSemanticStore';
import { AlwaysVisibleLaneIndicator } from '../AlwaysVisibleLaneIndicator';

describe('AlwaysVisibleLaneIndicator', () => {
  beforeEach(() => {
    act(() => {
      useChatStore.setState({
        actionMode: 'fast',
        sandboxMode: false,
        workspaceDir: null,
      });
      useLaneSemanticStore.setState({
        manualLaneOverride: null,
        pendingGraduation: null,
        isGraduationDialogOpen: false,
        graduationHistory: [],
      });
    });
  });

  it('renders chat lane indicator by default', () => {
    render(<AlwaysVisibleLaneIndicator />);
    const button = screen.getByRole('button', { name: /当前运行通道：快速对话通道/ });
    expect(button).toBeInTheDocument();
    expect(screen.getByText('快速对话通道')).toBeInTheDocument();
  });

  it('toggles inspection popover on click and reveals capabilities', () => {
    render(<AlwaysVisibleLaneIndicator />);
    const button = screen.getByRole('button', { name: /当前运行通道：快速对话通道/ });
    fireEvent.click(button);

    // Popover section is displayed
    const region = screen.getByRole('region', { name: '通道能力与环境详情' });
    expect(region).toBeInTheDocument();
    expect(screen.getByText('通道能力梯度：')).toBeInTheDocument();
    expect(screen.getByText('磁盘写入')).toBeInTheDocument();
    expect(screen.getByText('终端命令')).toBeInTheDocument();
    expect(screen.getByText('网页检索')).toBeInTheDocument();

    // In chat lane, upgrade button is visible
    const upgradeBtn = screen.getByRole('button', { name: '升级到工作区通道' });
    expect(upgradeBtn).toBeInTheDocument();

    // Clicking upgrade triggers openGraduationDialog
    fireEvent.click(upgradeBtn);
    expect(useLaneSemanticStore.getState().isGraduationDialogOpen).toBe(true);
  });

  it('reflects local workspace mode and displays workspace directory', () => {
    act(() => {
      useChatStore.setState({
        actionMode: 'agent',
        sandboxMode: false,
        workspaceDir: '/users/work/my-app',
      });
    });

    render(<AlwaysVisibleLaneIndicator />);
    expect(screen.getByText('本地工作区')).toBeInTheDocument();
    expect(screen.getByText('(my-app)')).toBeInTheDocument();

    const button = screen.getByRole('button', { name: /当前运行通道：本地工作区/ });
    fireEvent.click(button);

    expect(screen.getByText('/users/work/my-app')).toBeInTheDocument();
    // In workspace lane, upgrade button is not shown
    expect(screen.queryByRole('button', { name: '升级到工作区通道' })).not.toBeInTheDocument();
  });

  it('reflects cloud sandbox mode', () => {
    act(() => {
      useChatStore.setState({
        actionMode: 'agent',
        sandboxMode: true,
        workspaceDir: null,
      });
    });

    render(<AlwaysVisibleLaneIndicator />);
    expect(screen.getByText('云端沙箱工作区')).toBeInTheDocument();
  });
});
