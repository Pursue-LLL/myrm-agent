import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from '@/lib/api';
import {
  getCognitiveClockStatus,
  reportUserActivity,
  triggerT1SessionDebounce,
} from '@/services/memory';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('cognitive clock service api', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('fetches cognitive clock status', async () => {
    const mockStatus = {
      running: true,
      last_run: 1000,
      next_run: 2000,
      healthy_interval_hours: 6,
      unhealthy_interval_hours: 1,
      health_threshold: 70,
      seconds_until_next: 1000,
      consecutive_unhealthy: 0,
      last_pattern_discovery: 0,
      frequency_tier: 'balanced',
      quiet_window_enabled: false,
      quiet_window_start_hour: 0,
      quiet_window_end_hour: 6,
      timezone_offset_minutes: 0,
      local_hour: 12,
      within_quiet_window: false,
      seconds_until_quiet_window: 0,
      wakeup_grace_period_active: false,
      user_activity_detected: false,
      seconds_since_last_user_activity: 120,
    };
    apiRequestMock.mockResolvedValue(mockStatus);

    const result = await getCognitiveClockStatus();
    expect(apiRequestMock).toHaveBeenCalledWith('/memory/guardian/cognitive-clock/status');
    expect(result.running).toBe(true);
    expect(result.wakeup_grace_period_active).toBe(false);
  });

  it('reports user activity for cooperative yielding', async () => {
    apiRequestMock.mockResolvedValue({ status: 'ok', recorded: true, reason: 'typing' });

    const result = await reportUserActivity('sess-abc', 'typing');
    expect(apiRequestMock).toHaveBeenCalledWith(
      '/memory/guardian/cognitive-clock/activity',
      {
        method: 'POST',
        body: JSON.stringify({ session_id: 'sess-abc', reason: 'typing' }),
      }
    );
    expect(result.recorded).toBe(true);
  });

  it('triggers manual T1 session debounce', async () => {
    apiRequestMock.mockResolvedValue({ status: 'ok', session_id: 'sess-xyz' });

    const result = await triggerT1SessionDebounce('sess-xyz');
    expect(apiRequestMock).toHaveBeenCalledWith(
      '/memory/guardian/cognitive-clock/trigger-t1',
      {
        method: 'POST',
        body: JSON.stringify({ session_id: 'sess-xyz' }),
      }
    );
    expect(result.status).toBe('ok');
  });
});
