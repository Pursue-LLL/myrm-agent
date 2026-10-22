import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatSnapshotPerformanceMonitor } from '../ChatSnapshotPerformanceMonitor';
import { useAgentGranularCostStore } from '../useAgentGranularCostStore';

describe('ChatSnapshotPerformanceMonitor', () => {
  beforeEach(() => {
    useAgentGranularCostStore.getState().reset();
  });

  it('renders throttle monitor headers, live badge, and metric cards', () => {
    render(<ChatSnapshotPerformanceMonitor />);

    expect(screen.getByText('会话状态快照防卡顿节流引擎')).toBeInTheDocument();
    expect(screen.getByText('防抖生效中')).toBeInTheDocument();

    expect(screen.getByText('接收流式增量')).toBeInTheDocument();
    expect(screen.getByText('聚合提交快照')).toBeInTheDocument();
    expect(screen.getByText('消除冗余快照')).toBeInTheDocument();
    expect(screen.getByText('GC 压力削减率')).toBeInTheDocument();
  });

  it('updates throttle window when slider value changes', () => {
    render(<ChatSnapshotPerformanceMonitor />);

    const slider = screen.getByLabelText('动态节流窗口:');
    fireEvent.change(slider, { target: { value: '450' } });

    expect(useAgentGranularCostStore.getState().throttleConfig.throttleMs).toBe(450);
    expect(screen.getByText('450ms')).toBeInTheDocument();
  });

  it('handles immediate flush button click', () => {
    render(<ChatSnapshotPerformanceMonitor />);

    const flushBtn = screen.getByRole('button', { name: /立即冲刷/ });
    expect(flushBtn).toBeInTheDocument();

    fireEvent.click(flushBtn);
    // 验证冲刷不抛错，正常执行
  });
});
