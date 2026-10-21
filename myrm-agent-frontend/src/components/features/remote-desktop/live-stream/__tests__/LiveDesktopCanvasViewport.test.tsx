import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { LiveDesktopCanvasViewport } from '../LiveDesktopCanvasViewport';
import { useRemoteDesktopStore } from '../useRemoteDesktopStore';

describe('LiveDesktopCanvasViewport component', () => {
  beforeEach(() => {
    act(() => {
      useRemoteDesktopStore.getState().resetState();
    });
  });

  it('renders viewport header, sandbox id, metrics and canvas structure', () => {
    render(<LiveDesktopCanvasViewport />);

    expect(screen.getByTestId('live-desktop-canvas-viewport')).toBeInTheDocument();
    expect(screen.getByText('沙箱云电脑实时桌面')).toBeInTheDocument();
    expect(screen.getByText('sandbox-cloud-vm-8891')).toBeInTheDocument();
    expect(screen.getByText('低延迟推流中')).toBeInTheDocument();
    expect(screen.getByText('24ms')).toBeInTheDocument();
    expect(screen.getByText('30 FPS')).toBeInTheDocument();
    expect(screen.getByText('1920x1080')).toBeInTheDocument();
    expect(screen.getByTestId('desktop-stream-canvas')).toBeInTheDocument();
  });

  it('handles pause and resume stream actions via header button', () => {
    render(<LiveDesktopCanvasViewport />);

    const pauseBtn = screen.getByRole('button', { name: '暂停旁听画面' });
    fireEvent.click(pauseBtn);

    expect(useRemoteDesktopStore.getState().connectionState).toBe('paused');
    expect(screen.getByText('paused')).toBeInTheDocument();

    const resumeBtn = screen.getByRole('button', { name: '继续推流画面' });
    fireEvent.click(resumeBtn);

    expect(useRemoteDesktopStore.getState().connectionState).toBe('streaming');
    expect(screen.getByText('低延迟推流中')).toBeInTheDocument();
  });

  it('re-establishes connection when clicked in disconnected state', async () => {
    act(() => {
      useRemoteDesktopStore.getState().disconnectStream();
    });

    render(<LiveDesktopCanvasViewport />);
    expect(screen.getByText('disconnected')).toBeInTheDocument();

    const playBtn = screen.getByRole('button', { name: '继续推流画面' });
    await act(async () => {
      fireEvent.click(playBtn);
    });

    await waitFor(() => {
      expect(useRemoteDesktopStore.getState().connectionState).toBe('streaming');
    });
  });

  it('opens ephemeral share modal when share button is clicked', () => {
    render(<LiveDesktopCanvasViewport />);

    const shareBtn = screen.getByRole('button', {
      name: '生成时效安全免登录分享链接',
    });
    fireEvent.click(shareBtn);

    expect(useRemoteDesktopStore.getState().isShareModalOpen).toBe(true);
    expect(useRemoteDesktopStore.getState().currentTicket).not.toBeNull();
  });

  it('toggles human takeover mode and shows takeover badge overlay', () => {
    render(<LiveDesktopCanvasViewport />);

    const takeoverBtn = screen.getByRole('button', {
      name: '请求人工介入接管操作',
    });
    fireEvent.click(takeoverBtn);

    expect(useRemoteDesktopStore.getState().controlMode).toBe('human-takeover');
    expect(
      screen.getByText(/人工接管激活中：您的鼠标与键盘已直接映射至远程沙箱/)
    ).toBeInTheDocument();

    const releaseBtn = screen.getByRole('button', {
      name: '归还控制权给智能体',
    });
    fireEvent.click(releaseBtn);

    expect(useRemoteDesktopStore.getState().controlMode).toBe('observer');
  });

  it('toggles viewport expansion mode with responsive container styles', () => {
    render(<LiveDesktopCanvasViewport />);

    const toggleBtn = screen.getByRole('button', { name: '放大视窗' });
    fireEvent.click(toggleBtn);

    expect(useRemoteDesktopStore.getState().isExpanded).toBe(true);
    const viewport = screen.getByTestId('live-desktop-canvas-viewport');
    expect(viewport.className).toContain('max-w-5xl');

    const shrinkBtn = screen.getByRole('button', { name: '缩小视窗' });
    fireEvent.click(shrinkBtn);
    expect(useRemoteDesktopStore.getState().isExpanded).toBe(false);
  });

  it('renders virtual mouse cursor when action telemetry coordinates exist', () => {
    act(() => {
      useRemoteDesktopStore.getState().pushActionTelemetry({
        actionType: 'click',
        description: '精准定位提交表单按钮',
        coordinates: { x: 960, y: 540 },
      });
    });

    render(<LiveDesktopCanvasViewport />);
    const cursor = screen.getByTestId('virtual-mouse-cursor');

    expect(cursor).toBeInTheDocument();
    expect(cursor).toHaveStyle({ left: '50%', top: '50%' });
    expect(screen.getByText('精准定位提交表单按钮')).toBeInTheDocument();
  });
});
