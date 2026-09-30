import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { LoopStatusBar } from '../LoopStatusBar';
import * as sessionLoopService from '@/services/sessionLoop';

const stableT = (key: string, values?: Record<string, unknown>) => {
  if (key === 'loopScheduler.activeTitle') {
    return '自适应循环运行中';
  }
  if (key === 'loopScheduler.pausedTitle') {
    return '循环暂停 (用户输入中)';
  }
  if (key === 'loopScheduler.stop') {
    return '停止';
  }
  if (key === 'loopScheduler.stopping') {
    return '停止中...';
  }
  if (key === 'loopScheduler.backoffCount') {
    return `退避 x${values?.count}`;
  }
  if (key === 'loopScheduler.runsLimit') {
    return `第 ${values?.fired}/${values?.limit} 轮`;
  }
  if (key === 'loopScheduler.runs') {
    return `第 ${values?.fired} 轮`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/sessionLoop', () => ({
  getSessionLoopStatus: vi.fn(),
  stopSessionLoop: vi.fn(),
}));

describe('LoopStatusBar Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when session has no active loop', async () => {
    vi.mocked(sessionLoopService.getSessionLoopStatus).mockResolvedValue({
      chat_id: 'chat-test-1',
      is_active: false,
      status: 'none',
      mode: 'interval',
      prompt: '',
      current_delay_seconds: 60,
      current_delay_human: '1m',
      next_due_in_seconds: 0,
      next_due_in_human: '0s',
      ticks_fired: 0,
      times_limit: 0,
      until_condition: '',
      consecutive_unchanged: 0,
      last_stop_reason: null,
      paused_reason: null,
    });

    const { container } = render(<LoopStatusBar chatId="chat-test-1" />);

    await waitFor(() => {
      expect(screen.queryByTestId('session-loop-status-bar')).toBeNull();
      expect(container.firstChild).toBeNull();
    });
  });

  it('renders active loop capsule with prompt, countdown, and cadence', async () => {
    vi.mocked(sessionLoopService.getSessionLoopStatus).mockResolvedValue({
      chat_id: 'chat-test-2',
      is_active: true,
      status: 'active',
      mode: 'interval',
      prompt: 'Check CI build status',
      current_delay_seconds: 120,
      current_delay_human: '2m',
      next_due_in_seconds: 75,
      next_due_in_human: '1m 15s',
      ticks_fired: 3,
      times_limit: 10,
      until_condition: '',
      consecutive_unchanged: 2,
      last_stop_reason: null,
      paused_reason: null,
    });

    render(<LoopStatusBar chatId="chat-test-2" />);

    await waitFor(() => {
      expect(screen.getByTestId('session-loop-status-bar')).toBeDefined();
    });

    expect(screen.getByText('自适应循环运行中')).toBeDefined();
    expect(screen.getByText('Check CI build status')).toBeDefined();
    expect(screen.getByText('2m')).toBeDefined();
    expect(screen.getByText('退避 x2')).toBeDefined();
    expect(screen.getByText('第 3/10 轮')).toBeDefined();
    expect(screen.getByTestId('loop-countdown')).toBeDefined();
  });

  it('triggers stopSessionLoop when clicking stop button', async () => {
    vi.mocked(sessionLoopService.getSessionLoopStatus).mockResolvedValue({
      chat_id: 'chat-test-3',
      is_active: true,
      status: 'active',
      mode: 'interval',
      prompt: 'Monitor server logs',
      current_delay_seconds: 60,
      current_delay_human: '1m',
      next_due_in_seconds: 30,
      next_due_in_human: '30s',
      ticks_fired: 1,
      times_limit: 0,
      until_condition: '',
      consecutive_unchanged: 0,
      last_stop_reason: null,
      paused_reason: null,
    });

    vi.mocked(sessionLoopService.stopSessionLoop).mockResolvedValue({
      chat_id: 'chat-test-3',
      is_active: false,
      status: 'stopped',
      mode: 'interval',
      prompt: 'Monitor server logs',
      current_delay_seconds: 60,
      current_delay_human: '1m',
      next_due_in_seconds: 0,
      next_due_in_human: '0s',
      ticks_fired: 1,
      times_limit: 0,
      until_condition: '',
      consecutive_unchanged: 0,
      last_stop_reason: 'user_stopped',
      paused_reason: null,
    });

    render(<LoopStatusBar chatId="chat-test-3" />);

    await waitFor(() => {
      expect(screen.getByTestId('stop-session-loop-btn')).toBeDefined();
    });

    const stopBtn = screen.getByTestId('stop-session-loop-btn');
    fireEvent.click(stopBtn);

    await waitFor(() => {
      expect(sessionLoopService.stopSessionLoop).toHaveBeenCalledWith('chat-test-3', 'user_stopped');
    });
  });
});
