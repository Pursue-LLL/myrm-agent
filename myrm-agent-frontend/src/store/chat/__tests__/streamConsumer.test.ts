import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatActionsMethods, ChatActionsState } from '../messageRequest';
import { AgentBusyError, FatalNetworkError, consumeStream, executeStreamWithRetry } from '../streamConsumer';

const mockParseSseEnvelope = vi.hoisted(() => vi.fn());
const mockHandleMessageStream = vi.hoisted(() => vi.fn());
const mockCreateMessageRequest = vi.hoisted(() => vi.fn());
const mockAttachToChat = vi.hoisted(() => vi.fn());
const mockAttachForHitlRecovery = vi.hoisted(() => vi.fn());
const mockRecoverPendingApprovals = vi.hoisted(() => vi.fn());
const mockWaitUntilReady = vi.hoisted(() => vi.fn());
const mockLoadMessages = vi.hoisted(() => vi.fn());
const mockResolveE2eApiBase = vi.hoisted(() => vi.fn(() => null));
const approvalState = vi.hoisted(() => ({
  queue: [] as unknown[],
}));

vi.mock('../schema', () => ({
  parseSseEnvelope: (...args: unknown[]) => mockParseSseEnvelope(...args),
}));

vi.mock('../messageStreamHandler', () => ({
  handleMessageStream: (...args: unknown[]) => mockHandleMessageStream(...args),
}));

vi.mock('../messageRequest', () => ({
  createMessageRequest: (...args: unknown[]) => mockCreateMessageRequest(...args),
  attachToChat: (...args: unknown[]) => mockAttachToChat(...args),
  attachForHitlRecovery: (...args: unknown[]) => mockAttachForHitlRecovery(...args),
}));

vi.mock('../../useChatStore', () => ({
  default: {
    getState: () => ({
      loadMessages: mockLoadMessages,
    }),
  },
}));

vi.mock('@/hooks/usePendingApprovalsRecovery', () => ({
  recoverPendingApprovals: (...args: unknown[]) => mockRecoverPendingApprovals(...args),
}));

vi.mock('@/services/ConnectionManager', () => ({
  connectionManager: {
    waitUntilReady: (...args: unknown[]) => mockWaitUntilReady(...args),
  },
}));

vi.mock('@/lib/e2ee/client', () => ({
  decryptSseFrame: vi.fn(),
  loadStoredE2EESession: vi.fn(() => null),
}));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    resolveE2eApiBase: (...args: unknown[]) => mockResolveE2eApiBase(...args),
  };
});

vi.mock('@/store/useToolApprovalStore', () => ({
  default: {
    getState: () => approvalState,
  },
}));

const textEncoder = new TextEncoder();

function createBaseState(overrides: Partial<ChatActionsState> = {}): ChatActionsState {
  return {
    chatId: 'chat-stream-test',
    actionMode: 'agent',
    messages: [],
    messageAppeared: false,
    loading: true,
    files: [],
    ...overrides,
  } as unknown as ChatActionsState;
}

function createActions(state: ChatActionsState): ChatActionsMethods {
  return {
    setMessages: vi.fn((updater: (draft: ChatActionsState) => void) => updater(state)),
    setLoading: vi.fn(),
    setMessageAppeared: vi.fn(),
    setHideAttachList: vi.fn(),
    setHasUsedImagesInCurrentChat: vi.fn(),
    setSelectedModels: vi.fn(),
    setHasUserSelectedModel: vi.fn(),
    clearCurrentSessionMessageId: vi.fn(),
    _processSuggestions: vi.fn(async () => undefined),
    scheduleAutoSave: vi.fn(),
    setInputMessage: vi.fn(),
  } as unknown as ChatActionsMethods;
}

function createSseResponse(raw: string): Response {
  return new Response(raw, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

function createInterruptedResponse(rawChunk: string): Response {
  let emitted = false;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (!emitted) {
        emitted = true;
        controller.enqueue(textEncoder.encode(rawChunk));
        return;
      }
      throw new Error('reader exploded');
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

describe('streamConsumer resilience paths', () => {
  beforeEach(() => {
    mockParseSseEnvelope.mockReset();
    mockHandleMessageStream.mockReset();
    mockCreateMessageRequest.mockReset();
    mockAttachToChat.mockReset();
    mockAttachForHitlRecovery.mockReset();
    mockRecoverPendingApprovals.mockReset();
    mockWaitUntilReady.mockReset();
    mockLoadMessages.mockReset();
    mockResolveE2eApiBase.mockReset();
    mockResolveE2eApiBase.mockReturnValue(null);
    approvalState.queue = [];
    mockWaitUntilReady.mockResolvedValue({ ok: true });
    mockAttachForHitlRecovery.mockResolvedValue({
      ok: true,
      attached: false,
      queueLen: 0,
      source: 'none',
    });
    (window as Window & { __MYRM_E2E_DIRECT_SSE__?: boolean }).__MYRM_E2E_DIRECT_SSE__ = true;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('throws AgentBusyError immediately on 409 response', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(new Response('busy', { status: 409 }));

    await expect(
      executeStreamWithRetry('hello', 'msg-1', state, actions, null, abortController, false, ''),
    ).rejects.toBeInstanceOf(AgentBusyError);

    expect(mockCreateMessageRequest).toHaveBeenCalledTimes(1);
  });

  it('throws FatalNetworkError for non-retryable HTTP status', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'unauthorized' }), { status: 401 }),
    );

    await expect(
      executeStreamWithRetry('hello', 'msg-2', state, actions, null, abortController, false, ''),
    ).rejects.toBeInstanceOf(FatalNetworkError);

    expect(mockCreateMessageRequest).toHaveBeenCalledTimes(1);
  });

  it('retries transient HTTP and eventually succeeds', async () => {
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout').mockImplementation(
      ((handler: TimerHandler) => {
        if (typeof handler === 'function') {
          handler();
        }
        return 0 as unknown as ReturnType<typeof setTimeout>;
      }) as typeof setTimeout,
    );
    const state = createBaseState();
    const actions = createActions(state);
    const abortController = new AbortController();
    approvalState.queue = [{}];
    mockCreateMessageRequest
      .mockResolvedValueOnce(new Response('temporary', { status: 503 }))
      .mockResolvedValueOnce(createSseResponse('data: {"type":"message","messageId":"m-ok","data":"ok"}\n\n'));
    mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'm-ok', data: 'ok' });
    mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'ok' });

    try {
      await expect(
        executeStreamWithRetry('hello', 'msg-3', state, actions, null, abortController, false, ''),
      ).resolves.toBeUndefined();

      expect(mockCreateMessageRequest).toHaveBeenCalledTimes(2);
      expect(mockHandleMessageStream).toHaveBeenCalledTimes(1);
    } finally {
      setTimeoutSpy.mockRestore();
    }
  });

  it('attaches to running chat when stream is interrupted mid-read', async () => {
    const state = createBaseState({ chatId: 'chat-attach', actionMode: 'agent' });
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(
      createInterruptedResponse('data: {"type":"message","messageId":"m-attach","data":"hi"}\n\n'),
    );
    mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'm-attach', data: 'hi' });
    mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'hi' });
    mockAttachToChat.mockResolvedValue(true);

    await expect(
      executeStreamWithRetry('hello', 'msg-4', state, actions, null, abortController, false, ''),
    ).resolves.toBeUndefined();

    expect(mockAttachToChat).toHaveBeenCalledWith(
      'chat-attach',
      actions,
      expect.any(Function),
      expect.objectContaining({ allowWhileLoading: true }),
    );
  });

  it('falls back to loading messages when attach returns false after interruption', async () => {
    const state = createBaseState({ chatId: 'chat-load-fallback', actionMode: 'agent' });
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(
      createInterruptedResponse('data: {"type":"message","messageId":"m-fallback","data":"hi"}\n\n'),
    );
    mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'm-fallback', data: 'hi' });
    mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'hi' });
    mockAttachToChat.mockResolvedValue(false);
    mockLoadMessages.mockResolvedValue(undefined);

    await expect(
      executeStreamWithRetry('hello', 'msg-4b', state, actions, null, abortController, false, ''),
    ).resolves.toBeUndefined();

    expect(mockAttachToChat).toHaveBeenCalledTimes(1);
    expect(mockLoadMessages).toHaveBeenCalledWith('chat-load-fallback');
  });

  it('drops unknown SSE payload without calling message handler', async () => {
    const state = createBaseState({ loading: false });
    const actions = createActions(state);
    const abortController = new AbortController();
    mockParseSseEnvelope.mockReturnValue(null);

    const result = await consumeStream(
      createSseResponse('data: {"type":"unknown","messageId":"m-unknown"}\n\n'),
      'hello',
      state,
      actions,
      abortController,
      false,
      '',
    );

    expect(result.stoppedEarly).toBe(false);
    expect(mockHandleMessageStream).not.toHaveBeenCalled();
    expect(mockRecoverPendingApprovals).toHaveBeenCalledTimes(1);
  });

  it('throws timeout error when no data arrives for too long', async () => {
    const nowSpy = vi.spyOn(Date, 'now');
    nowSpy.mockReturnValueOnce(0).mockReturnValue(5 * 60 * 1000 + 1);

    const idleStream = new ReadableStream<Uint8Array>({
      start() {
        // no-op
      },
    });
    const response = new Response(idleStream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });
    const state = createBaseState({ loading: false });
    const actions = createActions(state);
    const abortController = new AbortController();

    try {
      await expect(
        consumeStream(response, 'hello', state, actions, abortController, false, ''),
      ).rejects.toThrow('Service response timeout');

      expect(mockRecoverPendingApprovals).toHaveBeenCalledTimes(1);
    } finally {
      nowSpy.mockRestore();
    }
  });
});
