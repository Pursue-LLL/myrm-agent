import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { LoopStatusBar } from '../LoopStatusBar';
import * as sessionLoopService from '@/services/sessionLoop';

// 带参数回显：同时验证翻译键与插值参数
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

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

    expect(screen.getByText('loopScheduler.activeTitle')).toBeDefined();
    expect(screen.getByText('Check CI build status')).toBeDefined();
    expect(screen.getByText('2m')).toBeDefined();
    expect(screen.getByText('loopScheduler.backoffCount:{"count":2}')).toBeDefined();
    expect(screen.getByText('loopScheduler.runsLimit:{"fired":3,"limit":10}')).toBeDefined();
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

  it('renders stop condition badge when until_condition is present', async () => {
    vi.mocked(sessionLoopService.getSessionLoopStatus).mockResolvedValue({
      chat_id: 'chat-test-until',
      is_active: true,
      status: 'active',
      mode: 'interval',
      prompt: 'Check deployment port',
      current_delay_seconds: 60,
      current_delay_human: '1m',
      next_due_in_seconds: 40,
      next_due_in_human: '40s',
      ticks_fired: 1,
      times_limit: 0,
      until_condition: 'port 8080 is open',
      consecutive_unchanged: 0,
      last_stop_reason: null,
      paused_reason: null,
    });

    render(<LoopStatusBar chatId="chat-test-until" />);

    await waitFor(() => {
      expect(screen.getByTestId('loop-until-badge')).toBeDefined();
    });

    expect(screen.getByText('loopScheduler.untilCondition:{"condition":"port 8080 is open"}')).toBeDefined();
  });

  it('shows the paused title without a countdown and counts unlimited runs', async () => {
    vi.mocked(sessionLoopService.getSessionLoopStatus).mockResolvedValue({
      chat_id: 'chat-test-paused',
      is_active: true,
      status: 'paused',
      mode: 'interval',
      prompt: 'Watch the queue',
      current_delay_seconds: 60,
      current_delay_human: '1m',
      next_due_in_seconds: 0,
      next_due_in_human: '0s',
      ticks_fired: 4,
      times_limit: 0,
      until_condition: '',
      consecutive_unchanged: 0,
      last_stop_reason: null,
      paused_reason: 'user_active',
    });

    render(<LoopStatusBar chatId="chat-test-paused" />);

    await waitFor(() => {
      expect(screen.getByTestId('session-loop-status-bar')).toBeDefined();
    });

    expect(screen.getByText('loopScheduler.pausedTitle')).toBeDefined();
    expect(screen.getByText('loopScheduler.runs:{"fired":4}')).toBeDefined();
    expect(screen.queryByTestId('loop-countdown')).toBeNull();
    expect(screen.getByText('loopScheduler.stop')).toBeDefined();
  });
});
