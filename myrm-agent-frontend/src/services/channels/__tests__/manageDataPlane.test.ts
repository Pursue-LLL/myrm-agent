import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '@/lib/api';
import { clearChannelDataPlane, getChannelDataPlaneStats } from '@/services/channels/manage';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

describe('manage channel data plane APIs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls getChannelDataPlaneStats with correct url', async () => {
    const mockStats = {
      channel: 'feishu',
      total_messages: 42,
      learning_eligible: 10,
      trigger_messages: 8,
      ambient_messages: 34,
      retention_days: 30,
      secret_scrubber_active: true,
    };
    vi.mocked(apiRequest).mockResolvedValueOnce(mockStats);

    const result = await getChannelDataPlaneStats('feishu');

    expect(apiRequest).toHaveBeenCalledWith('/channels/manage/feishu/data-plane');
    expect(result).toEqual(mockStats);
  });

  it('calls clearChannelDataPlane with correct payload when chatId is omitted', async () => {
    const mockClearResult = {
      channel: 'slack',
      deleted_count: 5,
      success: true,
    };
    vi.mocked(apiRequest).mockResolvedValueOnce(mockClearResult);

    const result = await clearChannelDataPlane('slack');

    expect(apiRequest).toHaveBeenCalledWith('/channels/manage/slack/data-plane/clear', {
      method: 'POST',
      body: JSON.stringify({ chat_id: null }),
    });
    expect(result).toEqual(mockClearResult);
  });

  it('calls clearChannelDataPlane with specific chatId when provided', async () => {
    const mockClearResult = {
      channel: 'slack',
      deleted_count: 2,
      success: true,
    };
    vi.mocked(apiRequest).mockResolvedValueOnce(mockClearResult);

    const result = await clearChannelDataPlane('slack', 'C123456');

    expect(apiRequest).toHaveBeenCalledWith('/channels/manage/slack/data-plane/clear', {
      method: 'POST',
      body: JSON.stringify({ chat_id: 'C123456' }),
    });
    expect(result.deleted_count).toBe(2);
  });
});
