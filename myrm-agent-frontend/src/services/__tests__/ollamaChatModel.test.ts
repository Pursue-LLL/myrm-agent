import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockApiRequest } = vi.hoisted(() => ({ mockApiRequest: vi.fn() }));

vi.mock('@/lib/api', () => ({ apiRequest: mockApiRequest }));

import { fetchOllamaChatModel } from '../ollamaChatModel';

describe('fetchOllamaChatModel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns the model with the address the server found it at', async () => {
    mockApiRequest.mockResolvedValue({ model: 'qwen3:8b', base_url: 'http://host.docker.internal:11434' });

    await expect(fetchOllamaChatModel()).resolves.toEqual({
      model: 'qwen3:8b',
      baseUrl: 'http://host.docker.internal:11434',
    });
  });

  it('asks quietly, so a failed probe never raises an error toast', async () => {
    mockApiRequest.mockResolvedValue({ model: null, base_url: 'http://localhost:11434' });

    await fetchOllamaChatModel();

    expect(mockApiRequest).toHaveBeenCalledExactlyOnceWith(
      '/integrations/ollama/chat-model',
      expect.objectContaining({ method: 'GET', silent: true }),
    );
  });

  it.each([
    ['no model qualifies', { model: null, base_url: 'http://localhost:11434' }],
    ['the model name is empty', { model: '', base_url: 'http://localhost:11434' }],
    ['the address is missing', { model: 'qwen3:8b' }],
    ['the answer is empty', {}],
  ])('returns null when %s', async (_label, answer) => {
    mockApiRequest.mockResolvedValue(answer);

    await expect(fetchOllamaChatModel()).resolves.toBeNull();
  });

  it('returns null when the request fails', async () => {
    mockApiRequest.mockRejectedValue(new Error('403 Not available in SaaS mode'));

    await expect(fetchOllamaChatModel()).resolves.toBeNull();
  });
});
