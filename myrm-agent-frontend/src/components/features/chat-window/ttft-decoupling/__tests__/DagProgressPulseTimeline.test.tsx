import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { DagProgressPulseTimeline } from '../DagProgressPulseTimeline';
import { useTtftDecouplingStore } from '../useTtftDecouplingStore';
import { DagTimelineState } from '../ttftDecouplingTypes';

describe('DagProgressPulseTimeline', () => {
  const baseTimeline: DagTimelineState = {
    dagId: 'dag-test-1',
    messageId: 'msg-001',
    totalSteps: 3,
    completedSteps: 2,
    isAllCompleted: false,
    startedAt: Date.now() - 3000,
    steps: [
      {
        id: 's1',
        name: '意图拆解与模型预路由',
        status: 'completed',
        isCriticalPath: true,
        elapsedMs: 80,
      },
      {
        id: 's2',
        name: '并发抓取知识库',
        status: 'completed',
        isCriticalPath: false,
        parallelGroupId: 'p-group-1',
        elapsedMs: 250,
      },
      {
        id: 's3',
        name: '并发抓取实时网络',
        status: 'running',
        isCriticalPath: false,
        parallelGroupId: 'p-group-1',
        elapsedMs: 620,
      },
    ],
  };

  beforeEach(() => {
    useTtftDecouplingStore.getState().reset();
    useTtftDecouplingStore.setState({
      activeDags: {
        'dag-test-1': baseTimeline,
      },
      isTimelineExpanded: {
        'dag-test-1': true,
      },
    });
  });

  it('renders progress summary and completed steps count', () => {
    render(<DagProgressPulseTimeline timeline={baseTimeline} />);

    expect(
      screen.getByTestId('dag-timeline-dag-test-1'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('DAG 关键路径执行流水线'),
    ).toBeInTheDocument();
    expect(screen.getByText(/2\/3 步完成 · 67%/)).toBeInTheDocument();
  });

  it('renders single node and parallel batch container', () => {
    render(<DagProgressPulseTimeline timeline={baseTimeline} />);

    expect(screen.getByTestId('dag-nodes-container')).toBeInTheDocument();
    expect(screen.getByText('意图拆解与模型预路由')).toBeInTheDocument();
    expect(screen.getByText('关键路径')).toBeInTheDocument();
    expect(
      screen.getByText(/并行执行批次 \(2 个任务并发\)/),
    ).toBeInTheDocument();
    expect(screen.getByText('并发抓取知识库')).toBeInTheDocument();
    expect(screen.getByText('并发抓取实时网络')).toBeInTheDocument();
    expect(screen.getByText('80ms')).toBeInTheDocument();
  });

  it('toggles expansion when header button is clicked', () => {
    render(<DagProgressPulseTimeline timeline={baseTimeline} />);

    expect(screen.getByTestId('dag-nodes-container')).toBeInTheDocument();

    const toggleBtn = screen.getByRole('button', {
      name: '收起关键路径时间轴',
    });
    act(() => {
      fireEvent.click(toggleBtn);
    });

    expect(screen.queryByTestId('dag-nodes-container')).toBeNull();
  });

  it('highlights critical path failure block', () => {
    const blockedTimeline: DagTimelineState = {
      ...baseTimeline,
      dagId: 'dag-blocked',
      steps: [
        {
          id: 's1',
          name: '关键规划步骤',
          status: 'failed',
          isCriticalPath: true,
        },
      ],
      totalSteps: 1,
      completedSteps: 0,
    };

    render(<DagProgressPulseTimeline timeline={blockedTimeline} />);
    expect(screen.getByText('关键规划步骤')).toBeInTheDocument();
  });
});
