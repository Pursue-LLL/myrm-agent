import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { InFlightBackgroundWorkerTray } from '../InFlightBackgroundWorkerTray';
import { useFullDuplexBridgeStore } from '../useFullDuplexBridgeStore';

describe('InFlightBackgroundWorkerTray', () => {
  beforeEach(() => {
    useFullDuplexBridgeStore.getState().reset();
  });

  it('renders nothing when activeWorkers is empty', () => {
    const { container } = render(<InFlightBackgroundWorkerTray />);
    expect(container.firstChild).toBeNull();
  });

  it('renders compact top capsule bar when workers are running', () => {
    act(() => {
      useFullDuplexBridgeStore.setState({
        activeWorkers: {
          w1: {
            id: 'w1',
            title: '全网深度竞品爬取',
            category: '竞品调研',
            status: 'running',
            progress: 45,
            currentStepLabel: '正在清洗数据',
            steps: [],
            elapsedSec: 60,
            estimatedTotalSec: 120,
            spawnedAt: Date.now(),
          },
        },
      });
    });

    render(<InFlightBackgroundWorkerTray />);

    expect(screen.getByTestId('in-flight-worker-tray')).toBeInTheDocument();
    expect(screen.getByText('后台长任务并发通道')).toBeInTheDocument();
    expect(screen.getByText(/1 个进行中 · 均度 45%/)).toBeInTheDocument();
    expect(screen.getByText(/全网深度竞品爬取/)).toBeInTheDocument();
  });

  it('toggles drawer panel to show details and steps', () => {
    act(() => {
      useFullDuplexBridgeStore.setState({
        activeWorkers: {
          w1: {
            id: 'w1',
            title: '高耗时代码编译',
            category: '构建',
            status: 'running',
            progress: 60,
            currentStepLabel: '输出构建中间产物',
            steps: [
              { id: 's1', label: '环境初始化', status: 'completed' },
              { id: 's2', label: '类型检查', status: 'running' },
            ],
            elapsedSec: 40,
            estimatedTotalSec: 100,
            spawnedAt: Date.now(),
          },
        },
      });
    });

    render(<InFlightBackgroundWorkerTray />);

    // 点击展开抽屉
    const expandBtn = screen.getByRole('button', { name: '展开后台任务抽屉' });
    act(() => {
      fireEvent.click(expandBtn);
    });

    expect(screen.getByTestId('worker-drawer-panel')).toBeInTheDocument();
    expect(screen.getByText(/在途与已就绪 Worker 任务队列/)).toBeInTheDocument();
    expect(screen.getByText('环境初始化')).toBeInTheDocument();
    expect(screen.getByText('类型检查')).toBeInTheDocument();

    // 点击取消任务
    const cancelBtn = screen.getByRole('button', { name: '取消任务' });
    act(() => {
      fireEvent.click(cancelBtn);
    });

    expect(useFullDuplexBridgeStore.getState().activeWorkers['w1']?.status).toBe(
      'canceled',
    );
  });

  it('removes completed task when trash button is clicked', () => {
    act(() => {
      useFullDuplexBridgeStore.setState({
        isTrayDrawerOpen: true,
        activeWorkers: {
          w1: {
            id: 'w1',
            title: '已结束的任务',
            category: '测试',
            status: 'completed',
            progress: 100,
            currentStepLabel: '完成',
            steps: [],
            elapsedSec: 30,
            estimatedTotalSec: 30,
            spawnedAt: Date.now(),
          },
        },
      });
    });

    render(<InFlightBackgroundWorkerTray />);

    const removeBtn = screen.getByRole('button', {
      name: '移除任务 已结束的任务',
    });
    act(() => {
      fireEvent.click(removeBtn);
    });

    expect(useFullDuplexBridgeStore.getState().activeWorkers['w1']).toBeUndefined();
  });
});
