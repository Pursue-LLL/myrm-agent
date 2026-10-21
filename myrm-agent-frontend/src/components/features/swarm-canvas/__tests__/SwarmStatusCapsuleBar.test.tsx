import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SwarmStatusCapsuleBar } from '../SwarmStatusCapsuleBar';
import { useSwarmCanvasStore } from '../useSwarmCanvasStore';
import type { SwarmWorkerItem } from '../swarmCanvasTypes';

describe('SwarmStatusCapsuleBar', () => {
  const mockWorkers: SwarmWorkerItem[] = [
    {
      id: 'w1',
      name: '爬虫',
      role: '采集',
      colorTheme: '#3b82f6',
      status: 'completed',
      currentTaskTitle: '抓取完成',
      progressPercent: 100,
      thinkingLogs: [],
      toolCalls: [],
      createdAt: Date.now(),
    },
    {
      id: 'w2',
      name: '沙盘',
      role: '运算',
      colorTheme: '#10b981',
      status: 'running',
      currentTaskTitle: '运算中',
      progressPercent: 50,
      thinkingLogs: [],
      toolCalls: [],
      createdAt: Date.now(),
    },
  ];

  beforeEach(() => {
    useSwarmCanvasStore.getState().resetAll();
  });

  it('正常渲染集群看板标题、总进度与状态摘要', () => {
    useSwarmCanvasStore.getState().setWorkers(mockWorkers);
    render(<SwarmStatusCapsuleBar />);

    expect(
      screen.getByTestId('swarm-status-capsule-bar')
    ).toBeInTheDocument();
    expect(
      screen.getByText('智能体军团协同看板')
    ).toBeInTheDocument();
    expect(screen.getByTestId('swarm-progress-badge')).toHaveTextContent(
      '总进度 75%'
    );
    expect(screen.getByTestId('swarm-status-text')).toHaveTextContent(
      '1 已达成 · 1 运行中'
    );
    expect(
      screen.getByTestId('swarm-running-pulse-dot')
    ).toBeInTheDocument();
  });

  it('支持点击状态过滤芯片切换过滤条件', () => {
    const handleFilterChange = vi.fn();
    useSwarmCanvasStore.getState().setWorkers(mockWorkers);
    render(<SwarmStatusCapsuleBar onFilterChange={handleFilterChange} />);

    const runningBtn = screen.getByTestId('filter-running-btn');
    fireEvent.click(runningBtn);

    expect(handleFilterChange).toHaveBeenCalledWith('running');
    expect(useSwarmCanvasStore.getState().statusFilter).toBe('running');

    const allBtn = screen.getByTestId('filter-all-btn');
    fireEvent.click(allBtn);

    expect(handleFilterChange).toHaveBeenCalledWith('all');
    expect(useSwarmCanvasStore.getState().statusFilter).toBe('all');
  });
});
