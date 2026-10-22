import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SideTrackForkTrigger } from '../SideTrackForkTrigger';
import { useSideTrackStore } from '../useSideTrackStore';
import { ReadOnlyStepSnapshot } from '../sideTrackTypes';

describe('SideTrackForkTrigger', () => {
  const mockStep: ReadOnlyStepSnapshot = {
    stepId: 'step-99',
    stepTitle: '自动化测试套件执行',
    toolAction: 'run_tests',
  };

  beforeEach(() => {
    useSideTrackStore.getState().clearSession();
  });

  it('renders compact trigger button by default and opens side track on click', () => {
    render(
      <SideTrackForkTrigger
        mainSessionId="session-xyz-123"
        mainTaskName="全栈模块持续集成"
        activeStep={mockStep}
      />
    );

    const triggerBtn = screen.getByTestId('side-track-fork-trigger-compact');
    expect(triggerBtn).toBeInTheDocument();
    expect(screen.getByText('开侧边问原理')).toBeInTheDocument();

    fireEvent.click(triggerBtn);

    const state = useSideTrackStore.getState();
    expect(state.isDrawerOpen).toBe(true);
    expect(state.activeSession?.mainSessionId).toBe('session-xyz-123');
    expect(state.activeSession?.snapshot.activeStep?.stepTitle).toBe('自动化测试套件执行');
  });

  it('renders full card trigger variant and indicates live active state', () => {
    render(
      <SideTrackForkTrigger
        variant="full"
        mainSessionId="session-abc-456"
        mainTaskName="高并发工作台构建"
        activeStep={mockStep}
      />
    );

    const fullBtn = screen.getByTestId('side-track-fork-trigger-full');
    expect(fullBtn).toBeInTheDocument();
    expect(screen.getByText('开侧边独立解释分支')).toBeInTheDocument();
    expect(
      screen.getByText(/主任务全速执行中 · 挂载当前瞬时代码快照 · 零上下文污染/)
    ).toBeInTheDocument();

    fireEvent.click(fullBtn);
    expect(useSideTrackStore.getState().isDrawerOpen).toBe(true);
  });
});
