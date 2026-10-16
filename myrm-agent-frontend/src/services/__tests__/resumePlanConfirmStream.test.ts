import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockFetchWithTimeout = vi.hoisted(() => vi.fn());
const session = vi.hoisted(() => ({
  chatId: 'chat-1' as string | null,
  modelSelection: { providerId: 'openai', model: 'test-model' } as { providerId: string; model: string } | null,
}));

vi.mock('@/lib/api', () => ({
  API_BASE_URL: '',
  apiRequest: vi.fn(),
  fetchWithTimeout: (...args: unknown[]) => mockFetchWithTimeout(...args),
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({
      chatId: session.chatId,
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
  getModelSelection: () => session.modelSelection,
  getLiteModelSelection: () => null,
}));

describe('resumePlanConfirmStream', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    session.chatId = 'chat-1';
    session.modelSelection = { providerId: 'openai', model: 'test-model' };
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

  it('rejects instead of reporting success when no chat is open', async () => {
    session.chatId = null;

    const { resumePlanConfirmStream } = await import('../chat');

    await expect(resumePlanConfirmStream('msg-plan-1', { action: 'confirm' })).rejects.toThrow(
      'Plan confirm resume needs an open chat',
    );
    expect(mockFetchWithTimeout).not.toHaveBeenCalled();
  });

  it('rejects instead of reporting success when no model is selected', async () => {
    session.modelSelection = null;

    const { resumePlanConfirmStream } = await import('../chat');

    await expect(resumePlanConfirmStream('msg-plan-1', { action: 'confirm' })).rejects.toThrow(
      'Plan confirm resume needs a selected model',
    );
    expect(mockFetchWithTimeout).not.toHaveBeenCalled();
  });
});
