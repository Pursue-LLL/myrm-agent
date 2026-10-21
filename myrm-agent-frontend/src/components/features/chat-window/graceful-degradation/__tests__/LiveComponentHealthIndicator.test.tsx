import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { LiveComponentHealthIndicator } from '../LiveComponentHealthIndicator';
import { useGracefulDegradationStore } from '../useGracefulDegradationStore';
import { ComponentHealthRecord } from '../gracefulDegradationTypes';

describe('LiveComponentHealthIndicator', () => {
  const healthyComp: ComponentHealthRecord = {
    id: 'c1',
    name: '主模型通道',
    type: 'model',
    status: 'closed',
    latencyMs: 280,
    errorRatePercent: 0,
    lastCheckedAt: Date.now(),
    fallbackStrategy: '多供应商轮换容灾',
  };

  const degradedComp: ComponentHealthRecord = {
    id: 'c2',
    name: '网络检索服务',
    type: 'search',
    status: 'half_open',
    latencyMs: 1450,
    errorRatePercent: 9.5,
    lastCheckedAt: Date.now(),
    failureReason: '触发频率限制',
    fallbackStrategy: '本地向量检索与事实记忆降级',
  };

  beforeEach(() => {
    useGracefulDegradationStore.getState().reset();
    useGracefulDegradationStore.setState({
      components: {
        c1: healthyComp,
      },
    });
  });

  it('renders healthy status indicator with latency badge', () => {
    render(<LiveComponentHealthIndicator />);

    expect(screen.getByText('系统健康')).toBeInTheDocument();
    expect(screen.getByText('280ms')).toBeInTheDocument();
  });

  it('opens and closes health diagnostic modal dialog', () => {
    render(<LiveComponentHealthIndicator />);

    // 点击打开模态视窗
    const triggerBtn = screen.getByRole('button', {
      name: '查看系统核心组件健康状态与断路器指标',
    });
    act(() => {
      fireEvent.click(triggerBtn);
    });

    expect(
      screen.getByTestId('health-diagnostic-modal'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('系统服务链路与熔断器健康透视'),
    ).toBeInTheDocument();
    expect(screen.getByText('主模型通道')).toBeInTheDocument();
    expect(screen.getByText(/多供应商轮换容灾/)).toBeInTheDocument();

    // 点击底部确定并关闭按钮
    const closeBottomBtn = screen.getByRole('button', {
      name: '确定并关闭',
    });
    act(() => {
      fireEvent.click(closeBottomBtn);
    });

    expect(
      screen.queryByTestId('health-diagnostic-modal'),
    ).toBeNull();
  });

  it('closes dialog on Escape key press', () => {
    useGracefulDegradationStore.setState({
      isHealthIndicatorModalOpen: true,
    });

    render(<LiveComponentHealthIndicator />);
    expect(screen.getByTestId('health-diagnostic-modal')).toBeInTheDocument();

    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });

    expect(screen.queryByTestId('health-diagnostic-modal')).toBeNull();
  });

  it('renders degraded status when a component has circuit breaker issues', () => {
    useGracefulDegradationStore.setState({
      components: {
        c1: healthyComp,
        c2: degradedComp,
      },
    });

    render(<LiveComponentHealthIndicator />);
    expect(screen.getByText('部分降级')).toBeInTheDocument();
  });
});
