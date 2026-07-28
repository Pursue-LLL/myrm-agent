import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatActionsMethods, ChatActionsState } from '../messageRequest';
import type { Message } from '@/store/chat/types';
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
const mockResolveChatWikiEvidenceContext = vi.hoisted(() => vi.fn());
const mockRecordWikiQuerySubmitted = vi.hoisted(() => vi.fn());
const mockConsumePendingChatWikiQuerySuccess = vi.hoisted(() => vi.fn());
const mockDecryptSseFrame = vi.hoisted(() => vi.fn());
const mockLoadStoredE2EESession = vi.hoisted(() => vi.fn(() => null));
const mockCreateMultiplexReadableStream = vi.hoisted(() => vi.fn());
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

vi.mock('../multiplexChunkBridge', () => ({
  createMultiplexReadableStream: (...args: unknown[]) => mockCreateMultiplexReadableStream(...args),
}));

vi.mock('../../useChatStore', () => ({
  default: {
    getState: () => ({
      loadMessages: mockLoadMessages,
    }),
  },
}));

vi.mock('@/hooks/approval/usePendingApprovalsRecovery', () => ({
  recoverPendingApprovals: (...args: unknown[]) => mockRecoverPendingApprovals(...args),
}));

vi.mock('@/services/ConnectionManager', () => ({
  connectionManager: {
    waitUntilReady: (...args: unknown[]) => mockWaitUntilReady(...args),
  },
}));

vi.mock('@/lib/e2ee/client', () => ({
  decryptSseFrame: (...args: unknown[]) => mockDecryptSseFrame(...args),
  loadStoredE2EESession: (...args: unknown[]) => mockLoadStoredE2EESession(...args),
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

vi.mock('@/services/wikiEvidenceContextCore', () => ({
  resolveChatWikiEvidenceContext: (...args: unknown[]) => mockResolveChatWikiEvidenceContext(...args),
}));

vi.mock('@/services/wikiEvidenceMetrics', () => ({
  recordWikiQuerySubmitted: (...args: unknown[]) => mockRecordWikiQuerySubmitted(...args),
}));

vi.mock('@/services/wikiEvidenceQuerySuccessPendingCore', () => ({
  consumePendingChatWikiQuerySuccess: (...args: unknown[]) => mockConsumePendingChatWikiQuerySuccess(...args),
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

function createChunkStream(raw: string): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(textEncoder.encode(raw));
      controller.close();
    },
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
    mockResolveChatWikiEvidenceContext.mockReset();
    mockRecordWikiQuerySubmitted.mockReset();
    mockConsumePendingChatWikiQuerySuccess.mockReset();
    mockDecryptSseFrame.mockReset();
    mockLoadStoredE2EESession.mockReset();
    mockCreateMultiplexReadableStream.mockReset();
    mockResolveE2eApiBase.mockReturnValue(null);
    mockResolveChatWikiEvidenceContext.mockReturnValue({ contextKey: 'chat:a-1', turnDistance: 0 });
    mockConsumePendingChatWikiQuerySuccess.mockReturnValue(undefined);
    mockLoadStoredE2EESession.mockReturnValue(null);
    mockCreateMultiplexReadableStream.mockImplementation(() => createChunkStream(''));
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

  it('throws AgentBusyError on HTTP 200 SSE error_type AgentBusyError (production path)', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    const abortController = new AbortController();
    const busyEvent = {
      type: 'error',
      error_type: 'AgentBusyError',
      status_code: 409,
      messageId: 'msg-busy-sse',
      data: 'Agent is busy processing another request for this session.',
    };
    mockCreateMessageRequest.mockResolvedValue(
      createSseResponse(`data: ${JSON.stringify(busyEvent)}\n\n`),
    );
    mockParseSseEnvelope.mockReturnValue(busyEvent);

    await expect(
      executeStreamWithRetry(
        'hello',
        'msg-busy-sse',
        state,
        actions,
        null,
        abortController,
        false,
        '',
      ),
    ).rejects.toBeInstanceOf(AgentBusyError);

    expect(mockHandleMessageStream).not.toHaveBeenCalled();
    expect(mockCreateMessageRequest).toHaveBeenCalledTimes(1);
  });

  it('throws AgentBusyError on multiplex POST when body is direct SSE busy envelope', async () => {
    const state = createBaseState({ chatId: 'chat-multiplex-busy', actionMode: 'agent' });
    const actions = createActions(state);
    const abortController = new AbortController();
    const busyEvent = {
      type: 'error',
      error_type: 'AgentBusyError',
      status_code: 409,
      messageId: 'msg-multiplex-busy',
      data: 'Agent is busy processing another request for this session.',
    };
    (window as Window & { __MYRM_E2E_DIRECT_SSE__?: boolean }).__MYRM_E2E_DIRECT_SSE__ = false;
    mockResolveE2eApiBase.mockReturnValue(null);
    mockCreateMultiplexReadableStream.mockReturnValue(createChunkStream(''));
    mockCreateMessageRequest.mockResolvedValue(
      createSseResponse(`data: ${JSON.stringify(busyEvent)}\n\n`),
    );
    mockParseSseEnvelope.mockReturnValue(busyEvent);

    await expect(
      executeStreamWithRetry(
        'hello',
        'msg-multiplex-busy',
        state,
        actions,
        null,
        abortController,
        false,
        '',
      ),
    ).rejects.toBeInstanceOf(AgentBusyError);

    expect(mockHandleMessageStream).not.toHaveBeenCalled();
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

  it('records wiki query success exactly once on first valid business frame', async () => {
    const state = createBaseState({
      chatId: 'chat-success',
      messages: [{ role: 'assistant', messageId: 'a-1', content: '', createdAt: new Date() } as Message],
    });
    const actions = createActions(state);
    const abortController = new AbortController();
    approvalState.queue = [{}];
    mockCreateMessageRequest.mockResolvedValueOnce(
      createSseResponse('data: {"type":"message","messageId":"msg-success","data":"ok"}\n\n'),
    );
    mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'msg-success', data: 'ok' });
    mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'ok' });

    await expect(
      executeStreamWithRetry(
        'hello',
        'msg-success',
        state,
        actions,
        null,
        abortController,
        false,
        '',
        undefined,
        undefined,
        true,
      ),
    ).resolves.toBeUndefined();

    expect(mockResolveChatWikiEvidenceContext).toHaveBeenCalledTimes(1);
    expect(mockResolveChatWikiEvidenceContext).toHaveBeenCalledWith(state.messages, 'chat-success');
    expect(mockRecordWikiQuerySubmitted).toHaveBeenCalledTimes(1);
    expect(mockRecordWikiQuerySubmitted).toHaveBeenCalledWith('chat', 'chat:a-1', 0);
  });

  it('does not record wiki query success when no valid business frame arrives', async () => {
    const state = createBaseState({
      chatId: 'chat-no-frame',
      messages: [{ role: 'assistant', messageId: 'a-1', content: '', createdAt: new Date() } as Message],
    });
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValueOnce(createSseResponse('data: not-json\n\n'));

    await expect(
      executeStreamWithRetry(
        'hello',
        'msg-no-frame',
        state,
        actions,
        null,
        abortController,
        false,
        '',
        undefined,
        undefined,
        true,
      ),
    ).resolves.toBeUndefined();

    expect(mockResolveChatWikiEvidenceContext).not.toHaveBeenCalled();
    expect(mockRecordWikiQuerySubmitted).not.toHaveBeenCalled();
  });

  it('records queued steer wiki query success on first matching business frame', async () => {
    const state = createBaseState({ chatId: 'chat-steer-success' });
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValueOnce(
      createSseResponse('data: {"type":"message","messageId":"msg-steer","data":"ok"}\n\n'),
    );
    mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'msg-steer', data: 'ok' });
    mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'ok' });
    mockConsumePendingChatWikiQuerySuccess.mockReturnValueOnce({
      contextKey: 'chat:steer',
      turnDistance: 2,
    });

    await expect(
      executeStreamWithRetry('hello', 'msg-steer', state, actions, null, abortController, false, ''),
    ).resolves.toBeUndefined();

    expect(mockConsumePendingChatWikiQuerySuccess).toHaveBeenCalledWith('chat-steer-success', 'msg-steer');
    expect(mockRecordWikiQuerySubmitted).toHaveBeenCalledTimes(1);
    expect(mockRecordWikiQuerySubmitted).toHaveBeenCalledWith('chat', 'chat:steer', 2);
    expect(mockResolveChatWikiEvidenceContext).not.toHaveBeenCalled();
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

  it('decrypts e2ee_frame chunks before parsing SSE payload', async () => {
    const state = createBaseState({ loading: false });
    const actions = createActions(state);
    const abortController = new AbortController();
    const session = { sessionId: 'e2ee-session' };
    mockLoadStoredE2EESession.mockReturnValue(session);
    mockDecryptSseFrame.mockReturnValue('data: {"type":"message","messageId":"m-e2ee","data":"secure"}\n\n');
    mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'm-e2ee', data: 'secure' });
    mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'secure' });

    await expect(
      consumeStream(
        createSseResponse('event: e2ee_frame\ndata: encrypted-frame\n\n'),
        'hello',
        state,
        actions,
        abortController,
        false,
        '',
      ),
    ).resolves.toMatchObject({ stoppedEarly: false });

    expect(mockDecryptSseFrame).toHaveBeenCalledWith(session, 'encrypted-frame');
    expect(mockHandleMessageStream).toHaveBeenCalledTimes(1);
  });

  it('uses accepted message_id from multiplex JSON handshake stream', async () => {
    const state = createBaseState({ chatId: 'chat-multiplex', actionMode: 'agent' });
    const actions = createActions(state);
    const abortController = new AbortController();
    const requestMessageId = 'msg-multiplex-request';
    const acceptedMessageId = 'msg-multiplex-accepted';
    approvalState.queue = [{}];
    mockResolveE2eApiBase.mockReturnValue('http://127.0.0.1:8080');
    (window as Window & { __MYRM_E2E_DIRECT_SSE__?: boolean }).__MYRM_E2E_DIRECT_SSE__ = false;

    mockCreateMultiplexReadableStream
      .mockImplementationOnce(() => createChunkStream(''))
      .mockImplementationOnce(() =>
        createChunkStream('data: {"type":"message","messageId":"m-multiplex","data":"ok"}\n\n'),
      );
    mockCreateMessageRequest.mockResolvedValue(
      new Response(JSON.stringify({ status: 'accepted', message_id: acceptedMessageId }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'm-multiplex', data: 'ok' });
    mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'ok' });

    await expect(
      executeStreamWithRetry(
        'hello',
        requestMessageId,
        state,
        actions,
        null,
        abortController,
        false,
        '',
      ),
    ).resolves.toBeUndefined();

    expect(mockCreateMultiplexReadableStream).toHaveBeenNthCalledWith(
      1,
      requestMessageId,
      abortController.signal,
    );
    expect(mockCreateMultiplexReadableStream).toHaveBeenNthCalledWith(
      2,
      acceptedMessageId,
      abortController.signal,
    );
    expect(mockHandleMessageStream).toHaveBeenCalledTimes(1);
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
