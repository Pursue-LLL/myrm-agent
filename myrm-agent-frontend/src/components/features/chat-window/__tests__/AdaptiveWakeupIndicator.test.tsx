import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  AdaptiveWakeupIndicator,
  WakeupBudgetStatus,
} from '../AdaptiveWakeupIndicator';

describe('AdaptiveWakeupIndicator', () => {
  const defaultStatus: WakeupBudgetStatus = {
    session_id: 'test-session-123',
    consecutive_wakes: 1,
    max_consecutive_wakes: 3,
    budget_remaining: 2,
    is_exhausted: false,
    is_user_stopped: false,
    host_activity: 'idle',
  };

  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'test-session-123',
        consecutive_wakes: 0,
        max_consecutive_wakes: 3,
        budget_remaining: 3,
        is_exhausted: false,
        is_user_stopped: false,
        host_activity: 'idle',
      }),
    } as unknown as Response);
  });

  it('renders followup active running state correctly', () => {
    render(
      <AdaptiveWakeupIndicator
        sessionId="test-session-123"
        initialStatus={defaultStatus}
        activeChannel="followup"
        sourceSummary="Background compile succeeded in 4.2s"
        sourceType="background_job"
      />,
    );

    expect(screen.getByText('自适应续跑进行中 (1/3)')).toBeInTheDocument();
    expect(screen.getByText('Background Job')).toBeInTheDocument();
    expect(
      screen.getByText('Background compile succeeded in 4.2s'),
    ).toBeInTheDocument();
    expect(screen.getByText('停止续跑')).toBeInTheDocument();
  });

  it('renders degradation state with reset CTA when budget is exhausted', async () => {
    const degradedStatus: WakeupBudgetStatus = {
      ...defaultStatus,
      consecutive_wakes: 3,
      budget_remaining: 0,
      is_exhausted: true,
    };
    const onReset = vi.fn();

    render(
      <AdaptiveWakeupIndicator
        sessionId="test-session-123"
        initialStatus={degradedStatus}
        activeChannel="degrade"
        onResetBudget={onReset}
      />,
    );

    expect(screen.getByText('连续自唤醒熔断保护 (3/3)')).toBeInTheDocument();
    expect(screen.getByText(/已达连续自动唤醒上限/)).toBeInTheDocument();
    const resetBtn = screen.getByText('重置预算');
    expect(resetBtn).toBeInTheDocument();

    fireEvent.click(resetBtn);
    await waitFor(() => {
      expect(onReset).toHaveBeenCalledWith('test-session-123');
    });
  });

  it('renders inject state when host is busy', () => {
    render(
      <AdaptiveWakeupIndicator
        sessionId="test-session-123"
        initialStatus={{ ...defaultStatus, host_activity: 'busy' }}
        activeChannel="inject"
        sourceType="subagent"
        sourceSummary="Subagent reviewer completed"
      />,
    );

    expect(screen.getByText('并发任务步骤合并 (宿主忙碌中)')).toBeInTheDocument();
    expect(screen.getByText('Subagent')).toBeInTheDocument();
    expect(screen.getByText('Subagent reviewer completed')).toBeInTheDocument();
  });

  it('renders suppress state when user requested stop', () => {
    const stoppedStatus: WakeupBudgetStatus = {
      ...defaultStatus,
      is_user_stopped: true,
    };

    render(
      <AdaptiveWakeupIndicator
        sessionId="test-session-123"
        initialStatus={stoppedStatus}
        activeChannel="suppress"
      />,
    );

    expect(screen.getByText('自动唤醒已抑制 (用户中止)')).toBeInTheDocument();
    expect(screen.queryByText('停止续跑')).not.toBeInTheDocument();
    expect(screen.queryByText('重置预算')).not.toBeInTheDocument();
  });

  it('triggers onStopWakeup callback when clicking stop button', async () => {
    const onStop = vi.fn();

    render(
      <AdaptiveWakeupIndicator
        sessionId="test-session-123"
        initialStatus={defaultStatus}
        activeChannel="followup"
        onStopWakeup={onStop}
      />,
    );

    const stopBtn = screen.getByText('停止续跑');
    fireEvent.click(stopBtn);
    await waitFor(() => {
      expect(onStop).toHaveBeenCalledWith('test-session-123');
    });
  });

  it('triggers onDismiss callback when clicking close button', () => {
    const onDismiss = vi.fn();

    render(
      <AdaptiveWakeupIndicator
        sessionId="test-session-123"
        initialStatus={defaultStatus}
        onDismiss={onDismiss}
      />,
    );

    const closeBtn = screen.getByLabelText('关闭指示卡片');
    fireEvent.click(closeBtn);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
