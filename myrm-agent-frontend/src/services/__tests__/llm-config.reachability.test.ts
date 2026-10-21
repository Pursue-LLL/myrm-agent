import { describe, expect, it, vi, beforeEach } from 'vitest';

import { checkModelReachability } from '../llm-config';

const apiRequestMock = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    apiRequest: (...args: unknown[]) => apiRequestMock(...args),
  };
});

describe('checkModelReachability', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('passes the failure classification and the upstream reason through', async () => {
    apiRequestMock.mockResolvedValue({
      data: {
        reachable: false,
        latency_ms: null,
        error: 'AuthenticationError: Invalid credential',
        error_kind: 'provider_error',
        cached: false,
      },
    });

    const result = await checkModelReachability({
      model: 'openai/muse-spark-1.3-contributor',
      api_key: 'sk-test',
      base_url: 'https://example.test/v1',
      model_kwargs: {},
    });

    expect(result.reachable).toBe(false);
    expect(result.error_kind).toBe('provider_error');
    expect(result.error).toBe('AuthenticationError: Invalid credential');
  });

  it('keeps the timeout classification when the probe ran out of time', async () => {
    apiRequestMock.mockResolvedValue({
      data: {
        reachable: false,
        latency_ms: null,
        error: 'No response within 15s',
        error_kind: 'timeout',
        cached: false,
      },
    });

    const result = await checkModelReachability({
      model: 'minimax/MiniMax-M3.1-Flash',
      api_key: 'sk-test',
      base_url: 'https://api.minimaxi.com/v1',
      model_kwargs: {},
    });

    expect(result.error_kind).toBe('timeout');
    expect(result.error).toBe('No response within 15s');
  });

  it('reports a network failure without a classification', async () => {
    apiRequestMock.mockRejectedValue(new Error('Network request failed'));

    const result = await checkModelReachability({
      model: 'minimax/MiniMax-M3.1-Flash',
      api_key: 'sk-test',
      base_url: 'https://api.minimaxi.com/v1',
      model_kwargs: {},
    });

    expect(result.reachable).toBe(false);
    expect(result.error_kind).toBeNull();
  });
});
