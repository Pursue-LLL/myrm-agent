import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProgressHUD } from '../ProgressHUD';
import { useCompanionPlanHubStore } from '../useCompanionPlanHubStore';

describe('ProgressHUD', () => {
  beforeEach(() => {
    useCompanionPlanHubStore.getState().resetAll();
  });

  it('未进入进度 HUD 模式时不渲染任何内容', () => {
    useCompanionPlanHubStore.setState({
      displayMode: 'pet_only',
      executionProgress: null,
    });
    const { container } = render(<ProgressHUD />);
    expect(container.firstChild).toBeNull();
  });

  it('进入进度模式时正常渲染胶囊条与步骤进度', () => {
    useCompanionPlanHubStore.setState({
      displayMode: 'progress_hud',
      executionProgress: {
        activePlanId: 'p-1',
        currentStepIndex: 2,
        totalSteps: 4,
        currentStepTitle: '正在拉取经营数据流',
        elapsedSeconds: 45,
        logs: ['[INFO] 开始拉取数据'],
      },
    });

    render(<ProgressHUD />);
    expect(
      screen.getByTestId('companion-progress-hud')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('progress-hud-capsule')
    ).toBeInTheDocument();
    expect(screen.getByTestId('progress-hud-label')).toHaveTextContent(
      '正在拉取经营数据流 (2/4)'
    );
    expect(screen.getByText('00:45')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('点击展开/收起日志按钮，展开并展示实时步骤流', () => {
    useCompanionPlanHubStore.setState({
      displayMode: 'progress_hud',
      executionProgress: {
        activePlanId: 'p-1',
        currentStepIndex: 1,
        totalSteps: 2,
        currentStepTitle: '初始化',
        elapsedSeconds: 10,
        logs: ['初始化环境完成', '加载 Pandas 运行时'],
      },
    });

    render(<ProgressHUD />);
    const toggleBtn = screen.getByTestId('toggle-hud-logs-btn');
    expect(screen.queryByTestId('hud-logs-drawer')).not.toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.getByTestId('hud-logs-drawer')).toBeInTheDocument();
    expect(screen.getByText('加载 Pandas 运行时')).toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId('hud-logs-drawer')).not.toBeInTheDocument();
  });

  it('点击展开主工作台按钮触发回调', () => {
    const handleOpenMain = vi.fn();
    useCompanionPlanHubStore.setState({
      displayMode: 'progress_hud',
      executionProgress: {
        currentStepIndex: 1,
        totalSteps: 1,
        currentStepTitle: '执行中',
        elapsedSeconds: 5,
        logs: [],
      },
    });

    render(<ProgressHUD onOpenMainWindow={handleOpenMain} />);
    const openMainBtn = screen.getByTestId('hud-open-main-btn');
    fireEvent.click(openMainBtn);
    expect(handleOpenMain).toHaveBeenCalledTimes(1);
  });

  it('点击叫停按钮触发 onStop 并退出 HUD 模式', () => {
    const handleStop = vi.fn();
    useCompanionPlanHubStore.setState({
      displayMode: 'progress_hud',
      executionProgress: {
        currentStepIndex: 1,
        totalSteps: 1,
        currentStepTitle: '执行中',
        elapsedSeconds: 5,
        logs: [],
      },
    });

    render(<ProgressHUD onStop={handleStop} />);
    const stopBtn = screen.getByTestId('hud-stop-btn');
    fireEvent.click(stopBtn);

    expect(handleStop).toHaveBeenCalledTimes(1);
    expect(useCompanionPlanHubStore.getState().displayMode).toBe('pet_only');
  });
});
