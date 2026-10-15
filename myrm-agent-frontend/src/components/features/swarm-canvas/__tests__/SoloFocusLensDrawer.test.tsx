import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SoloFocusLensDrawer } from '../SoloFocusLensDrawer';
import { useSwarmCanvasStore } from '../useSwarmCanvasStore';
import type { SwarmWorkerItem } from '../swarmCanvasTypes';

describe('SoloFocusLensDrawer', () => {
  const mockWorker: SwarmWorkerItem = {
    id: 'worker-lens-01',
    name: '全网情报分析师',
    role: '外部信源采集专员',
    colorTheme: '#3b82f6',
    status: 'running',
    currentTaskTitle: '抓取 Qoder 实测评测数据',
    progressPercent: 75,
    thinkingLogs: ['解析文章 DOM 结构', '提取核心亮点'],
    toolCalls: [
      { id: 'c1', toolName: 'web_crawler', summary: '抓取网页', durationMs: 250 },
    ],
    createdAt: Date.now(),
  };

  beforeEach(() => {
    useSwarmCanvasStore.getState().resetAll();
  });

  it('未打开抽屉或无匹配 worker 时不渲染任何内容', () => {
    useSwarmCanvasStore.setState({
      isLensDrawerOpen: false,
      focusedWorkerId: null,
    });
    const { container } = render(<SoloFocusLensDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('激活时正常渲染抽屉头部、思维流列表与工具调用轨迹', () => {
    useSwarmCanvasStore.setState({
      workers: [mockWorker],
      focusedWorkerId: 'worker-lens-01',
      isLensDrawerOpen: true,
    });

    render(<SoloFocusLensDrawer />);
    expect(
      screen.getByTestId('solo-focus-lens-drawer')
    ).toBeInTheDocument();
    expect(screen.getByText('全网情报分析师')).toBeInTheDocument();
    expect(
      screen.getByTestId('lens-thinking-logs-list')
    ).toBeInTheDocument();
    expect(screen.getByText('解析文章 DOM 结构')).toBeInTheDocument();
    expect(screen.getByText('提取核心亮点')).toBeInTheDocument();
    expect(
      screen.getByTestId('lens-tool-calls-list')
    ).toBeInTheDocument();
    expect(screen.getByText('web_crawler')).toBeInTheDocument();
  });

  it('输入人工纠偏指令并发送，触发 steer 回调', () => {
    const handleSteer = vi.fn();
    useSwarmCanvasStore.setState({
      workers: [mockWorker],
      focusedWorkerId: 'worker-lens-01',
      isLensDrawerOpen: true,
    });

    render(<SoloFocusLensDrawer onSteer={handleSteer} />);
    const steerInput = screen.getByTestId('lens-steer-input');
    fireEvent.change(steerInput, {
      target: { value: '请过滤掉广告内容' },
    });

    const sendBtn = screen.getByTestId('lens-send-steer-btn');
    fireEvent.click(sendBtn);

    expect(handleSteer).toHaveBeenCalledWith(
      'worker-lens-01',
      '请过滤掉广告内容'
    );
  });

  it('点击叫停按钮触发 onStop 回调', () => {
    const handleStop = vi.fn();
    useSwarmCanvasStore.setState({
      workers: [mockWorker],
      focusedWorkerId: 'worker-lens-01',
      isLensDrawerOpen: true,
    });

    render(<SoloFocusLensDrawer onStop={handleStop} />);
    const stopBtn = screen.getByTestId('lens-stop-worker-btn');
    fireEvent.click(stopBtn);

    expect(handleStop).toHaveBeenCalledWith('worker-lens-01');
    const worker = useSwarmCanvasStore.getState().workers[0];
    expect(worker.status).toBe('failed');
  });

  it('点击关闭按钮收起透镜抽屉并触发 onClose', () => {
    const handleClose = vi.fn();
    useSwarmCanvasStore.setState({
      workers: [mockWorker],
      focusedWorkerId: 'worker-lens-01',
      isLensDrawerOpen: true,
    });

    render(<SoloFocusLensDrawer onClose={handleClose} />);
    const closeBtn = screen.getByTestId('close-lens-drawer-btn');
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(useSwarmCanvasStore.getState().isLensDrawerOpen).toBe(false);
  });
});
