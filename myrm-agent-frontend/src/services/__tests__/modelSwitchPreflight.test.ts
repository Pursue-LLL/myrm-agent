import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchModelSwitchPreflight } from '@/services/llm-config';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api';

const mockApiRequest = vi.mocked(apiRequest);

describe('fetchModelSwitchPreflight', () => {
  beforeEach(() => {
    mockApiRequest.mockReset();
  });

  it('posts estimated_tokens, ratio, prompt_mode, turn_count, chat_id and models to the preflight endpoint', async () => {
    mockApiRequest.mockResolvedValue({
      results: [
        {
          model: 'custom/a',
          found: true,
          new_window: 16000,
          compress_threshold: 8266,
          will_compress: true,
        },
      ],
    });

    const result = await fetchModelSwitchPreflight(
      9000,
      [{ model: 'custom/a', max_input_tokens: 16000 }],
      0.3,
      'lean',
      7,
      'chat-123',
    );

    expect(mockApiRequest).toHaveBeenCalledWith('/integrations/llm/model-switch-preflight', {
      method: 'POST',
      body: JSON.stringify({
        estimated_tokens: 9000,
        compress_start_ratio: 0.3,
        prompt_mode: 'lean',
        turn_count: 7,
        chat_id: 'chat-123',
        models: [{ model: 'custom/a', max_input_tokens: 16000 }],
      }),
    });
    expect(result['custom/a']?.will_compress).toBe(true);
  });

  it('omits compress_start_ratio when not provided', async () => {
    mockApiRequest.mockResolvedValue({ results: [] });

    await fetchModelSwitchPreflight(1000, [{ model: 'custom/b', max_input_tokens: 32000 }]);

    const body = JSON.parse((mockApiRequest.mock.calls[0][1] as { body: string }).body);
    expect(body.compress_start_ratio).toBeNull();
    expect(body.prompt_mode).toBeNull();
    expect(body.turn_count).toBeNull();
    expect(body.chat_id).toBeNull();
  });

  it('isolates cache across chat sessions', async () => {
    mockApiRequest.mockResolvedValue({ results: [] });

    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }], null, null, null, 'chat-1');
    mockApiRequest.mockReset();
    mockApiRequest.mockResolvedValue({ results: [] });
    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }], null, null, null, 'chat-2');

    expect(mockApiRequest).toHaveBeenCalledTimes(1);
  });

  it('returns cached results when key is unchanged', async () => {
    const payload = {
      results: [
        {
          model: 'custom/a',
          found: true,
          new_window: 16000,
          compress_threshold: 8266,
          will_compress: true,
        },
      ],
    };
    mockApiRequest.mockResolvedValue(payload);

    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }]);
    mockApiRequest.mockReset();
    const second = await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }]);

    expect(mockApiRequest).not.toHaveBeenCalled();
    expect(second['custom/a']?.will_compress).toBe(true);
  });

  it('re-fetches when estimated_tokens changes (session switch)', async () => {
    const payload = {
      results: [
        {
          model: 'custom/a',
          found: true,
          new_window: 16000,
          compress_threshold: 8266,
          will_compress: false,
        },
      ],
    };
    mockApiRequest.mockResolvedValue(payload);

    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }]);
    mockApiRequest.mockReset();
    mockApiRequest.mockResolvedValue(payload);
    await fetchModelSwitchPreflight(1000, [{ model: 'custom/a', max_input_tokens: 16000 }]);

    expect(mockApiRequest).toHaveBeenCalledTimes(1);
  });

  it('re-fetches when max_input_tokens changes', async () => {
    mockApiRequest.mockResolvedValue({ results: [] });

    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }]);
    mockApiRequest.mockReset();
    mockApiRequest.mockResolvedValue({ results: [] });
    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 32000 }]);

    expect(mockApiRequest).toHaveBeenCalledTimes(1);
  });

  it('re-fetches when prompt_mode changes', async () => {
    mockApiRequest.mockResolvedValue({ results: [] });

    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }], null, 'full');
    mockApiRequest.mockReset();
    mockApiRequest.mockResolvedValue({ results: [] });
    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }], null, 'lean');

    expect(mockApiRequest).toHaveBeenCalledTimes(1);
  });

  it('re-fetches when turn_count changes (session turns grow)', async () => {
    mockApiRequest.mockResolvedValue({ results: [] });

    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }], null, null, 3);
    mockApiRequest.mockReset();
    mockApiRequest.mockResolvedValue({ results: [] });
    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }], null, null, 10);

    expect(mockApiRequest).toHaveBeenCalledTimes(1);
  });

  it('re-fetches when compress_start_ratio changes', async () => {
    mockApiRequest.mockResolvedValue({ results: [] });

    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }], 0.3);
    mockApiRequest.mockReset();
    mockApiRequest.mockResolvedValue({ results: [] });
    await fetchModelSwitchPreflight(9000, [{ model: 'custom/a', max_input_tokens: 16000 }], 0.6);

    expect(mockApiRequest).toHaveBeenCalledTimes(1);
  });

  it('bounded cache evicts oldest entries at the limit', async () => {
    const payload = (model: string) => ({
      results: [
        {
          model,
          found: true,
          new_window: 16000,
          compress_threshold: 8266,
          will_compress: true,
        },
      ],
    });
    mockApiRequest.mockImplementation(async () => ({ results: [] }));

    // Fill past the LRU limit with unique keys.
    const LIMIT = 100;
    for (let i = 0; i < LIMIT + 5; i++) {
      mockApiRequest.mockResolvedValue(payload(`custom/m-${i}`));
      await fetchModelSwitchPreflight(i, [{ model: `custom/m-${i}`, max_input_tokens: 16000 }]);
    }

    // The earliest keys were evicted -> re-requesting them hits the network again.
    mockApiRequest.mockReset();
    mockApiRequest.mockResolvedValue({ results: [] });
    await fetchModelSwitchPreflight(0, [{ model: 'custom/m-0', max_input_tokens: 16000 }]);
    expect(mockApiRequest).toHaveBeenCalledTimes(1);

    // A recently-cached key still hits the cache.
    mockApiRequest.mockReset();
    await fetchModelSwitchPreflight(LIMIT + 4, [{ model: `custom/m-${LIMIT + 4}`, max_input_tokens: 16000 }]);
    expect(mockApiRequest).not.toHaveBeenCalled();
  });

  it('returns partial results when the request fails', async () => {
    mockApiRequest.mockRejectedValue(new Error('network'));
    const result = await fetchModelSwitchPreflight(9000, [{ model: 'custom/network-fail', max_input_tokens: 16000 }]);
    expect(result).toEqual({});
  });
});
