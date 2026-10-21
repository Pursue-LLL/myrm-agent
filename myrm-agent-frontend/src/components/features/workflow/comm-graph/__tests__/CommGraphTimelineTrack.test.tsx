import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { CommGraphTimelineTrack } from '../CommGraphTimelineTrack';
import { useCommGraphStore } from '../useCommGraphStore';

describe('CommGraphTimelineTrack', () => {
  beforeEach(() => {
    act(() => {
      useCommGraphStore.getState().resetState();
    });
  });

  it('当 events 为空时不渲染任何 DOM', () => {
    const { container } = render(<CommGraphTimelineTrack />);
    expect(container.firstChild).toBeNull();
  });

  it('渲染事件步骤时间轴与当前选定事件的协同通信载荷', () => {
    act(() => {
      useCommGraphStore.getState().addCommEvent({
        stepIndex: 1,
        fromAgent: 'CoordinatorAgent',
        toAgent: 'ArchitectAgent',
        action: 'dispatch_arch_spec',
        payloadSummary: '系统微服务拆分架构白皮书',
        status: 'completed',
        latencyMs: 38,
      });
    });

    render(<CommGraphTimelineTrack />);

    expect(screen.getByText('协同流水线事件 (1)')).toBeInTheDocument();
    expect(screen.getByText('步骤 #1')).toBeInTheDocument();
    expect(screen.getAllByText('dispatch_arch_spec').length).toBeGreaterThan(0);
    expect(screen.getByText('CoordinatorAgent')).toBeInTheDocument();
    expect(screen.getByText('ArchitectAgent')).toBeInTheDocument();
    expect(screen.getByText(/系统微服务拆分架构白皮书/)).toBeInTheDocument();
    expect(screen.getByText('38ms')).toBeInTheDocument();
  });

  it('点击步骤切换当前选定事件，并通过 Live 按钮完成双向游标记忆跳跃与原位回溯', () => {
    let id1 = '';
    let id2 = '';
    act(() => {
      id1 = useCommGraphStore.getState().addCommEvent({
        stepIndex: 1,
        fromAgent: 'AgentA',
        toAgent: 'AgentB',
        action: 'step_one',
        payloadSummary: '第一阶段结果',
        status: 'completed',
      });
      id2 = useCommGraphStore.getState().addCommEvent({
        stepIndex: 2,
        fromAgent: 'AgentB',
        toAgent: 'AgentC',
        action: 'step_two',
        payloadSummary: '第二阶段结果',
        status: 'completed',
      });
    });

    render(<CommGraphTimelineTrack />);

    // 手动选定第 1 步
    const step1Btn = screen.getByRole('button', { name: /1 step_one/i });
    act(() => {
      fireEvent.click(step1Btn);
    });

    expect(useCommGraphStore.getState().selectedEventId).toBe(id1);
    expect(useCommGraphStore.getState().isLive).toBe(false);
    expect(screen.getByText('历史审阅模式 (已暂停自动跟随)')).toBeInTheDocument();

    // 点击切入 Live
    const liveBtn = screen.getByRole('button', { name: '切入实时追踪最新事件' });
    act(() => {
      fireEvent.click(liveBtn);
    });

    // 验证切入 Live 成功，当前选定事件跃迁至最新的 id2
    expect(useCommGraphStore.getState().isLive).toBe(true);
    expect(useCommGraphStore.getState().selectedEventId).toBe(id2);
    expect(useCommGraphStore.getState().returnCursorId).toBe(id1);
    expect(screen.getByText(/Live 实时跟随中/)).toBeInTheDocument();

    // 再次点击 Live 按钮退出，验证原位回溯至 id1
    const exitLiveBtn = screen.getByRole('button', {
      name: '退出实时追踪模式并回溯历史游标',
    });
    act(() => {
      fireEvent.click(exitLiveBtn);
    });

    expect(useCommGraphStore.getState().isLive).toBe(false);
    expect(useCommGraphStore.getState().selectedEventId).toBe(id1);
    expect(screen.getByText('第一阶段结果')).toBeInTheDocument();
  });
});
