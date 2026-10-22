import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { CommandCenterQuickTriggerButton } from '../CommandCenterQuickTriggerButton';
import { useCommandCenterHudStore } from '../useCommandCenterHudStore';

describe('CommandCenterQuickTriggerButton', () => {
  beforeEach(() => {
    useCommandCenterHudStore.getState().reset();
  });

  it('renders trigger button with health indicator and shortcut key badge', () => {
    render(<CommandCenterQuickTriggerButton />);

    expect(screen.getByRole('button', { name: '打开 Command Center 全局运维大厅' })).toBeInTheDocument();
    expect(screen.getByText('Command Center')).toBeInTheDocument();
    expect(screen.getByTitle('系统与网关服务连接完好')).toBeInTheDocument();
  });

  it('toggles HUD open state on click', () => {
    render(<CommandCenterQuickTriggerButton />);

    const btn = screen.getByRole('button', { name: '打开 Command Center 全局运维大厅' });
    expect(useCommandCenterHudStore.getState().isOpen).toBe(false);

    fireEvent.click(btn);
    expect(useCommandCenterHudStore.getState().isOpen).toBe(true);

    fireEvent.click(btn);
    expect(useCommandCenterHudStore.getState().isOpen).toBe(false);
  });

  it('reflects degraded and offline gateway health statuses', () => {
    act(() => {
      useCommandCenterHudStore.setState({ gatewayHealth: 'degraded' });
    });
    const { rerender } = render(<CommandCenterQuickTriggerButton />);

    expect(screen.getByTitle('网关存在部分告警或轻度降级')).toBeInTheDocument();

    act(() => {
      useCommandCenterHudStore.setState({ gatewayHealth: 'offline' });
    });
    rerender(<CommandCenterQuickTriggerButton />);

    expect(screen.getByTitle('网关或本地服务离线')).toBeInTheDocument();
  });
});
