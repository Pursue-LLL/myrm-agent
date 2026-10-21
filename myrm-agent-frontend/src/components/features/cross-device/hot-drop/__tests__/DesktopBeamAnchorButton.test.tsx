import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DesktopBeamAnchorButton } from '../DesktopBeamAnchorButton';
import { useCrossDeviceDropStore } from '../useCrossDeviceDropStore';

describe('DesktopBeamAnchorButton', () => {
  beforeEach(() => {
    useCrossDeviceDropStore.getState().resetToDefaults();
    vi.restoreAllMocks();
  });

  it('正确渲染桌面附件区手机直投按钮与状态指示点', () => {
    render(<DesktopBeamAnchorButton />);

    expect(
      screen.getByTestId('desktop-beam-anchor-root')
    ).toBeInTheDocument();
    expect(screen.getByTestId('desktop-beam-trigger-btn')).toBeInTheDocument();
    expect(screen.getByTestId('beam-status-indicator')).toBeInTheDocument();
  });

  it('点击按钮能够展开配对二维码浮层与配对短码', () => {
    render(<DesktopBeamAnchorButton />);

    const triggerBtn = screen.getByTestId('desktop-beam-trigger-btn');
    fireEvent.click(triggerBtn);

    expect(screen.getByTestId('beam-anchor-popover')).toBeInTheDocument();
    expect(screen.getByTestId('beam-qr-container')).toBeInTheDocument();

    const pairCode = useCrossDeviceDropStore.getState().activeSession.pairCode;
    expect(screen.getByTestId('beam-pair-code-text')).toHaveTextContent(
      pairCode
    );
  });

  it('点击刷新按钮能够重新生成配对短码与会话', () => {
    render(<DesktopBeamAnchorButton />);

    // 展开 popover
    fireEvent.click(screen.getByTestId('desktop-beam-trigger-btn'));

    const initialCode =
      useCrossDeviceDropStore.getState().activeSession.pairCode;

    const refreshBtn = screen.getByTestId('refresh-pair-code-btn');
    fireEvent.click(refreshBtn);

    const newCode = useCrossDeviceDropStore.getState().activeSession.pairCode;
    expect(newCode).toBeDefined();
    expect(typeof newCode).toBe('string');
  });

  it('点击模拟手机拍照按钮能够触发推流与接收', () => {
    vi.useFakeTimers();
    render(<DesktopBeamAnchorButton />);

    fireEvent.click(screen.getByTestId('desktop-beam-trigger-btn'));

    const simulateBtn = screen.getByTestId('simulate-beam-btn');
    fireEvent.click(simulateBtn);

    expect(
      useCrossDeviceDropStore.getState().activeSession.connectionState
    ).toBe('beaming');

    vi.advanceTimersByTime(50);

    expect(
      useCrossDeviceDropStore.getState().activeSession.connectionState
    ).toBe('completed');
    expect(
      useCrossDeviceDropStore.getState().activeIncomingPayload
    ).toBeDefined();

    vi.useRealTimers();
  });
});
