import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from '@/lib/api';
import {
  getMemoryHealth,
  getMemoryGuardianOverview,
  getMemoryGuardianMorningDigest,
  triggerMemoryMaintenance,
  type MemoryGuardianPolicy,
  updateMemoryGuardianPolicy,
} from '@/services/memory';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('memory guardian service api', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('posts safe trigger mode by default', async () => {
    apiRequestMock.mockResolvedValue({ triggered: true, mode: 'safe', applied: false });

    await triggerMemoryMaintenance();

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/guardian/trigger', {
      method: 'POST',
      body: JSON.stringify({ mode: 'safe' }),
    });
  });

  it('posts force trigger mode when requested', async () => {
    apiRequestMock.mockResolvedValue({ triggered: true, mode: 'force', applied: true });

    await triggerMemoryMaintenance('force');

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/guardian/trigger', {
      method: 'POST',
      body: JSON.stringify({ mode: 'force' }),
    });
  });

  it('updates guardian policy via PUT', async () => {
    const policy: MemoryGuardianPolicy = {
      frequency_tier: 'balanced',
      quiet_window_enabled: true,
      quiet_window_start_hour: 23,
      quiet_window_end_hour: 7,
      timezone_offset_minutes: 480,
    };
    apiRequestMock.mockResolvedValue(policy);

    await updateMemoryGuardianPolicy(policy);

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/guardian/policy', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(policy),
    });
  });

  it('loads morning digest using silent mode', async () => {
    apiRequestMock.mockResolvedValue({ available: false });
    const timezoneOffsetMinutes = -new Date().getTimezoneOffset();

    await getMemoryGuardianMorningDigest();

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/guardian/morning-digest', {
      silent: true,
      headers: { 'x-client-timezone-offset-minutes': String(timezoneOffsetMinutes) },
    });
  });

  it('loads health with client timezone header', async () => {
    apiRequestMock.mockResolvedValue({
      health: { total: 80, dimensions: {}, suggestions: [], has_graph: false },
      guardian: {},
      policy: {},
    });
    const timezoneOffsetMinutes = -new Date().getTimezoneOffset();

    await getMemoryHealth();

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/guardian/health', {
      headers: { 'x-client-timezone-offset-minutes': String(timezoneOffsetMinutes) },
    });
  });

  it('loads overview with client timezone header in silent mode', async () => {
    apiRequestMock.mockResolvedValue({
      health: { total: 80, dimensions: {}, suggestions: [], has_graph: false },
      guardian: {},
      policy: {},
      digest: { available: false },
    });
    const timezoneOffsetMinutes = -new Date().getTimezoneOffset();

    await getMemoryGuardianOverview();

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/guardian/overview', {
      silent: true,
      headers: { 'x-client-timezone-offset-minutes': String(timezoneOffsetMinutes) },
    });
  });
});
