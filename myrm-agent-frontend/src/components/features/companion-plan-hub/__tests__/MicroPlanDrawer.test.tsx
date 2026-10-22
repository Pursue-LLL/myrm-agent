import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MicroPlanDrawer } from '../MicroPlanDrawer';
import { useCompanionPlanHubStore } from '../useCompanionPlanHubStore';
import type { MicroPlanDraft } from '../companionPlanHubTypes';

describe('MicroPlanDrawer', () => {
  const mockPlan: MicroPlanDraft = {
    planId: 'plan-123',
    goal: '店长端经营看板构建',
    targetAgentName: '全栈架构师',
    estimatedMinutes: 6,
    createdAt: Date.now(),
    subtasks: [
      { id: 't1', title: '指标定义', status: 'pending', required: true, order: 1 },
      { id: 't2', title: '图表生成', status: 'pending', required: false, order: 2 },
    ],
  };

  beforeEach(() => {
    useCompanionPlanHubStore.getState().resetAll();
  });

  it('未激活计划时不渲染任何内容', () => {
    useCompanionPlanHubStore.setState({ displayMode: 'pet_only', activePlan: null });
    const { container } = render(<MicroPlanDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('激活时正常渲染计划抽屉、业务目标输入框与步骤清单', () => {
    useCompanionPlanHubStore.getState().setActivePlan(mockPlan);
    render(<MicroPlanDrawer />);

    expect(screen.getByTestId('micro-plan-drawer')).toBeInTheDocument();
    expect(screen.getByTestId('plan-goal-input')).toBeInTheDocument();
    expect(screen.getByTestId('subtask-item-t1')).toBeInTheDocument();
    expect(screen.getByTestId('subtask-item-t2')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-launch-plan-btn')).toBeInTheDocument();
  });

  it('支持微调核心业务目标', () => {
    useCompanionPlanHubStore.getState().setActivePlan(mockPlan);
    render(<MicroPlanDrawer />);

    const input = screen.getByTestId('plan-goal-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '经营看板加急版' } });
    expect(useCompanionPlanHubStore.getState().refinedGoal).toBe('经营看板加急版');
  });

  it('支持跳过可选子任务，必选子任务跳过按钮置灰禁用', () => {
    useCompanionPlanHubStore.getState().setActivePlan(mockPlan);
    render(<MicroPlanDrawer />);

    const reqBtn = screen.getByTestId('toggle-skip-subtask-t1');
    expect(reqBtn).toBeDisabled();

    const optBtn = screen.getByTestId('toggle-skip-subtask-t2');
    expect(optBtn).not.toBeDisabled();

    fireEvent.click(optBtn);
    const subtasks = useCompanionPlanHubStore.getState().activePlan?.subtasks ?? [];
    expect(subtasks[1].status).toBe('skipped');
  });

  it('点击确认开工按钮，触发回调并流转进入进度 HUD 模式', () => {
    const handleConfirm = vi.fn();
    useCompanionPlanHubStore.getState().setActivePlan(mockPlan);
    render(<MicroPlanDrawer onConfirmLaunch={handleConfirm} />);

    const confirmBtn = screen.getByTestId('confirm-launch-plan-btn');
    fireEvent.click(confirmBtn);

    expect(handleConfirm).toHaveBeenCalledWith('plan-123', '店长端经营看板构建');
    expect(useCompanionPlanHubStore.getState().displayMode).toBe('progress_hud');
  });

  it('点击关闭按钮收起抽屉', () => {
    const handleClose = vi.fn();
    useCompanionPlanHubStore.getState().setActivePlan(mockPlan);
    render(<MicroPlanDrawer onClose={handleClose} />);

    const closeBtn = screen.getByTestId('close-plan-drawer-btn');
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(useCompanionPlanHubStore.getState().displayMode).toBe('pet_only');
  });
});
