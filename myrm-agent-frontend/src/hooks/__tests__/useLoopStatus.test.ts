import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { useLoopStatus } from '../useLoopStatus';
import * as sessionLoopService from '@/services/sessionLoop';

vi.mock('@/services/sessionLoop', () => ({
  getSessionLoopStatus: vi.fn(),
  stopSessionLoop: vi.fn(),
}));

describe('useLoopStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches status on mount and returns inactive state when no loop is running', async () => {
    vi.mocked(sessionLoopService.getSessionLoopStatus).mockResolvedValue({
      chat_id: 'chat_123',
      is_active: false,
      status: 'none',
      mode: 'interval',
      prompt: '',
      current_delay_seconds: 0,
      current_delay_human: '',
      next_due_in_seconds: 0,
      next_due_in_human: '',
      ticks_fired: 0,
      times_limit: 0,
      until_condition: '',
      consecutive_unchanged: 0,
      last_stop_reason: null,
      paused_reason: null,
    });

    const { result } = renderHook(() => useLoopStatus('chat_123'));

    await waitFor(() => {
      expect(result.current.status).not.toBeNull();
    });

    expect(result.current.status?.is_active).toBe(false);
    expect(result.current.countdown).toBe(0);
  });

  it('immediately refetches status when session-loop-changed event is dispatched', async () => {
    vi.mocked(sessionLoopService.getSessionLoopStatus)
      .mockResolvedValueOnce({
        chat_id: 'chat_123',
        is_active: false,
        status: 'none',
        mode: 'interval',
        prompt: '',
        current_delay_seconds: 0,
        current_delay_human: '',
        next_due_in_seconds: 0,
        next_due_in_human: '',
        ticks_fired: 0,
        times_limit: 0,
        until_condition: '',
        consecutive_unchanged: 0,
        last_stop_reason: null,
        paused_reason: null,
      })
      .mockResolvedValueOnce({
        chat_id: 'chat_123',
        is_active: true,
        status: 'active',
        mode: 'interval',
        prompt: 'check deploy',
        current_delay_seconds: 300,
        current_delay_human: '5m',
        next_due_in_seconds: 300,
        next_due_in_human: '5m',
        ticks_fired: 1,
        times_limit: 0,
        until_condition: '',
        consecutive_unchanged: 0,
        last_stop_reason: null,
        paused_reason: null,
      });

    const { result } = renderHook(() => useLoopStatus('chat_123'));

    await waitFor(() => {
      expect(result.current.status?.is_active).toBe(false);
    });

    act(() => {
      window.dispatchEvent(
        new CustomEvent('session-loop-changed', {
          detail: { chatId: 'chat_123' },
        }),
      );
    });

    await waitFor(() => {
      expect(result.current.status?.is_active).toBe(true);
      expect(result.current.status?.prompt).toBe('check deploy');
      expect(result.current.countdown).toBe(300);
    });

    expect(sessionLoopService.getSessionLoopStatus).toHaveBeenCalledTimes(2);
  });
});
