import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ElasticSwarmCanvas } from '../ElasticSwarmCanvas';
import { useSwarmCanvasStore } from '../useSwarmCanvasStore';
import type { SwarmWorkerItem } from '../swarmCanvasTypes';

describe('ElasticSwarmCanvas', () => {
  const mockWorkers: SwarmWorkerItem[] = [
    {
      id: 'worker-1',
      name: '情报爬虫',
      role: '全网采集',
      colorTheme: '#3b82f6',
      status: 'running',
      currentTaskTitle: '抓取竞品架构分析',
      progressPercent: 70,
      thinkingLogs: ['解析 HTML AST', '写入本地向量库'],
      toolCalls: [{ id: 't1', toolName: 'web_crawler', summary: 'fetch' }],
      createdAt: Date.now(),
    },
    {
      id: 'worker-2',
      name: '精算沙盘',
      role: '因果推演',
      colorTheme: '#10b981',
      status: 'completed',
      currentTaskTitle: '产业链敏感度计算完毕',
      progressPercent: 100,
      thinkingLogs: ['推演结束'],
      toolCalls: [],
      createdAt: Date.now(),
    },
  ];

  beforeEach(() => {
    useSwarmCanvasStore.getState().resetAll();
  });

  it('列表为空时渲染友好的空状态占位', () => {
    useSwarmCanvasStore.setState({ workers: [] });
    render(<ElasticSwarmCanvas />);
    expect(
      screen.getByTestId('elastic-swarm-canvas-empty')
    ).toBeInTheDocument();
  });

  it('渲染弹性网格容器与每个子智能体卡片', () => {
    useSwarmCanvasStore.getState().setWorkers(mockWorkers);
    render(<ElasticSwarmCanvas />);

    expect(
      screen.getByTestId('elastic-swarm-canvas')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('swarm-grid-container')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('worker-card-worker-1')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('worker-card-worker-2')
    ).toBeInTheDocument();

    expect(screen.getByText('情报爬虫')).toBeInTheDocument();
    expect(screen.getByText('抓取竞品架构分析')).toBeInTheDocument();
    expect(screen.getByText('写入本地向量库')).toBeInTheDocument();
    expect(screen.getByText('70%')).toBeInTheDocument();
  });

  it('点击智能体卡片触发聚焦透镜并触发回调', () => {
    const handleWorkerClick = vi.fn();
    useSwarmCanvasStore.getState().setWorkers(mockWorkers);
    render(<ElasticSwarmCanvas onWorkerClick={handleWorkerClick} />);

    const card = screen.getByTestId('worker-card-worker-1');
    fireEvent.click(card);

    expect(handleWorkerClick).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'worker-1',
        name: '情报爬虫',
      })
    );
    expect(useSwarmCanvasStore.getState().focusedWorkerId).toBe('worker-1');
    expect(useSwarmCanvasStore.getState().isLensDrawerOpen).toBe(true);
  });
});
