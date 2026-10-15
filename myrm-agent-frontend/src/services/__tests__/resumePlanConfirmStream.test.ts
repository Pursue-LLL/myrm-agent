import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockFetchWithTimeout = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api', () => ({
  API_BASE_URL: '',
  apiRequest: vi.fn(),
  fetchWithTimeout: (...args: unknown[]) => mockFetchWithTimeout(...args),
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({
      chatId: 'chat-1',
      actionMode: 'agent',
      agentConfig: null,
      messages: [],
      messageAppeared: false,
      loading: false,
    }),
    setState: vi.fn(),
  },
}));

vi.mock('@/store/chat/messageRequest', () => ({
  getModelSelection: () => ({ providerId: 'openai', model: 'test-model' }),
  getLiteModelSelection: () => null,
}));

describe('resumePlanConfirmStream', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('rejects when the timeout already answered the plan confirmation (HTTP 409)', async () => {
    mockFetchWithTimeout.mockResolvedValue(new Response('{}', { status: 409 }));

    const { resumePlanConfirmStream } = await import('../chat');

    await expect(resumePlanConfirmStream('msg-plan-1', { action: 'confirm' })).rejects.toThrow(
      'Plan confirmation has already been resolved by timeout',
    );
  });

  it('rejects with the HTTP status for other failures', async () => {
    mockFetchWithTimeout.mockResolvedValue(new Response('boom', { status: 500 }));

    const { resumePlanConfirmStream } = await import('../chat');

    await expect(resumePlanConfirmStream('msg-plan-1', { action: 'confirm' })).rejects.toThrow(
      'Plan confirm resume failed: HTTP 500',
    );
  });
});
