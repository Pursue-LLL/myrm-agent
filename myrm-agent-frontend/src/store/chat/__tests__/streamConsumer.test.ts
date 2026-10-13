import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatActionsMethods, ChatActionsState } from '../messageRequest';
import type { Message } from '@/store/chat/types';
import { FatalNetworkError } from '@/lib/utils/networkResilience';
import { consumeStream } from '../consumeStream';
import { AgentBusyError, RequestRefusedError } from '../streamErrors';
import { executeStreamWithRetry } from '../streamConsumer';

const mockParseSseEnvelope = vi.hoisted(() => vi.fn());
const mockHandleMessageStream = vi.hoisted(() => vi.fn());
const mockCreateMessageRequest = vi.hoisted(() => vi.fn());
const mockAttachToChat = vi.hoisted(() => vi.fn());
const mockAttachForHitlRecovery = vi.hoisted(() => vi.fn());
const mockRecoverPendingApprovals = vi.hoisted(() => vi.fn());
const mockWaitUntilReady = vi.hoisted(() => vi.fn());
const mockLoadMessages = vi.hoisted(() => vi.fn());
const mockReleaseTurnInspectorControls = vi.hoisted(() => vi.fn());
const mockResolveE2eApiBase = vi.hoisted(() => vi.fn<(...args: unknown[]) => string | null>(() => null));
const mockResolveChatWikiEvidenceContext = vi.hoisted(() => vi.fn());
const mockRecordWikiQuerySubmitted = vi.hoisted(() => vi.fn());
const mockConsumePendingChatWikiQuerySuccess = vi.hoisted(() => vi.fn());
const mockDecryptSseFrame = vi.hoisted(() => vi.fn());
const mockLoadStoredE2EESession = vi.hoisted(() => vi.fn<(...args: unknown[]) => unknown>(() => null));
const mockCreateMultiplexReadableStream = vi.hoisted(() => vi.fn());
const mockClearPendingWorkflowTemplate = vi.hoisted(() => vi.fn());
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

vi.mock('@/lib/inspector/releaseTurnInspectorControls', () => ({
  releaseTurnInspectorControls: (...args: unknown[]) => mockReleaseTurnInspectorControls(...args),
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

vi.mock('@/services/wiki/evidenceContextCore', () => ({
  resolveChatWikiEvidenceContext: (...args: unknown[]) => mockResolveChatWikiEvidenceContext(...args),
}));

vi.mock('@/services/wiki/evidenceMetrics', () => ({
  recordWikiQuerySubmitted: (...args: unknown[]) => mockRecordWikiQuerySubmitted(...args),
}));

vi.mock('@/services/wiki/evidenceQuerySuccessPendingCore', () => ({
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
    clearPendingWorkflowTemplate: mockClearPendingWorkflowTemplate,
    setIsWorkflowMode: vi.fn(),
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

const STOP_TEST_EVENT = 'data: {"type":"message","messageId":"m-stop","data":"hi"}\n\n';

/** One event, then silence: like the multiplex bridge, it neither closes nor errors by itself once its turn is stopped. */
function createSilentResponse(onCancel: () => void = () => undefined): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(textEncoder.encode(STOP_TEST_EVENT));
    },
    cancel: onCancel,
  });
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

/** One event, then a read failure the moment the turn is stopped: how an aborted fetch body behaves. */
function createAbortFailingResponse(signal: AbortSignal): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(textEncoder.encode(STOP_TEST_EVENT));
      signal.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')), {
        once: true,
      });
    },
  });
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

/** Watches a promise without awaiting it, so a test can assert that it has (not) settled yet. */
function observe(promise: Promise<unknown>): { isSettled: () => boolean; error: () => unknown } {
  let settled = false;
  let failure: unknown;
  promise.then(
    () => {
      settled = true;
    },
    (error: unknown) => {
      settled = true;
      failure = error;
    },
  );
  return { isSettled: () => settled, error: () => failure };
}

/** Polls an expectation; the generous timeout keeps these timer-driven tests stable on a loaded machine. */
function eventually(assertion: () => void): Promise<void> {
  return vi.waitFor(assertion, { timeout: 5_000 });
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
    mockReleaseTurnInspectorControls.mockReset();
    mockResolveE2eApiBase.mockReset();
    mockResolveChatWikiEvidenceContext.mockReset();
    mockRecordWikiQuerySubmitted.mockReset();
    mockConsumePendingChatWikiQuerySuccess.mockReset();
    mockDecryptSseFrame.mockReset();
    mockLoadStoredE2EESession.mockReset();
    mockCreateMultiplexReadableStream.mockReset();
    mockClearPendingWorkflowTemplate.mockReset();
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

  it('keeps pending workflow template armed when agent-stream POST fails', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(new Response('busy', { status: 409 }));

    await expect(
      executeStreamWithRetry('hello', 'msg-template-armed', state, actions, null, abortController, false, ''),
    ).rejects.toBeInstanceOf(AgentBusyError);

    expect(mockClearPendingWorkflowTemplate).not.toHaveBeenCalled();
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
    mockCreateMessageRequest.mockResolvedValue(createSseResponse(`data: ${JSON.stringify(busyEvent)}\n\n`));
    mockParseSseEnvelope.mockReturnValue(busyEvent);

    await expect(
      executeStreamWithRetry('hello', 'msg-busy-sse', state, actions, null, abortController, false, ''),
    ).rejects.toBeInstanceOf(AgentBusyError);

    expect(mockHandleMessageStream).not.toHaveBeenCalled();
    expect(mockCreateMessageRequest).toHaveBeenCalledTimes(1);
  });

  it('throws AgentBusyError through the REAL parseSseEnvelope on 200 SSE busy (regression)', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    const abortController = new AbortController();
    const busyEvent = {
      type: 'error',
      error_type: 'AgentBusyError',
      status_code: 409,
      messageId: 'msg-busy-real',
      data: 'Agent is busy processing another request for this session.',
    };
    const schema = await vi.importActual<typeof import('../schema')>('../schema');
    mockParseSseEnvelope.mockImplementation(schema.parseSseEnvelope);
    mockCreateMessageRequest.mockResolvedValue(createSseResponse(`data: ${JSON.stringify(busyEvent)}\n\n`));

    await expect(
      executeStreamWithRetry('hello', 'msg-busy-real', state, actions, null, abortController, false, ''),
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
    mockCreateMessageRequest.mockResolvedValue(createSseResponse(`data: ${JSON.stringify(busyEvent)}\n\n`));
    mockParseSseEnvelope.mockReturnValue(busyEvent);

    await expect(
      executeStreamWithRetry('hello', 'msg-multiplex-busy', state, actions, null, abortController, false, ''),
    ).rejects.toBeInstanceOf(AgentBusyError);

    expect(mockHandleMessageStream).not.toHaveBeenCalled();
    expect(mockCreateMessageRequest).toHaveBeenCalledTimes(1);
  });

  it('throws RequestRefusedError (a FatalNetworkError) for non-retryable HTTP status', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'unauthorized' }), { status: 401 }),
    );

    const failure = await executeStreamWithRetry(
      'hello',
      'msg-2',
      state,
      actions,
      null,
      abortController,
      false,
      '',
    ).then(
      () => null,
      (error: unknown) => error,
    );

    expect(failure).toBeInstanceOf(RequestRefusedError);
    expect(failure).toBeInstanceOf(FatalNetworkError);
    expect(mockCreateMessageRequest).toHaveBeenCalledTimes(1);
  });

  it('retries transient HTTP and eventually succeeds', async () => {
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout').mockImplementation(((handler: TimerHandler) => {
      if (typeof handler === 'function') {
        handler();
      }
      return 0 as unknown as ReturnType<typeof setTimeout>;
    }) as unknown as typeof setTimeout);
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
    // Task still running after attach: inspector control must be preserved.
    expect(mockReleaseTurnInspectorControls).not.toHaveBeenCalled();
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
    // Task finished during disconnect: inspector control must be released
    // alongside the final state fetch so the UI cannot stay "controlling".
    expect(mockReleaseTurnInspectorControls).toHaveBeenCalledTimes(1);
    expect(mockReleaseTurnInspectorControls).toHaveBeenCalledWith('chat-load-fallback');
  });

  it('releases inspector control even when the final state fetch fails after attach false', async () => {
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout').mockImplementation(((handler: TimerHandler) => {
      if (typeof handler === 'function') {
        handler();
      }
      return 0 as unknown as ReturnType<typeof setTimeout>;
    }) as unknown as typeof setTimeout);
    const state = createBaseState({ chatId: 'chat-load-fail', actionMode: 'agent' });
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(
      createInterruptedResponse('data: {"type":"message","messageId":"m-fail","data":"hi"}\n\n'),
    );
    mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'm-fail', data: 'hi' });
    mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'hi' });
    mockAttachToChat.mockResolvedValue(false);
    mockLoadMessages.mockRejectedValue(new Error('network down'));

    try {
      await expect(
        executeStreamWithRetry('hello', 'msg-fail', state, actions, null, abortController, false, ''),
      ).rejects.toThrow();
      // Attach false already proved the task ended: the inspector release must
      // not depend on the subsequent final-state fetch succeeding.
      expect(mockReleaseTurnInspectorControls).toHaveBeenCalled();
      expect(mockReleaseTurnInspectorControls).toHaveBeenCalledWith('chat-load-fail');
    } finally {
      setTimeoutSpy.mockRestore();
    }
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
      executeStreamWithRetry('hello', requestMessageId, state, actions, null, abortController, false, ''),
    ).resolves.toBeUndefined();

    expect(mockCreateMultiplexReadableStream).toHaveBeenNthCalledWith(1, requestMessageId, abortController.signal);
    expect(mockCreateMultiplexReadableStream).toHaveBeenNthCalledWith(2, acceptedMessageId, abortController.signal);
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

  it('consumes protocol heartbeat without schema parsing or warnings', async () => {
    const state = createBaseState({ loading: false });
    const actions = createActions(state);
    const abortController = new AbortController();
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    try {
      await consumeStream(
        createSseResponse('event: heartbeat\ndata: null\n\n'),
        'hello',
        state,
        actions,
        abortController,
        false,
        '',
      );
    } finally {
      warnSpy.mockRestore();
    }

    expect(mockParseSseEnvelope).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
    expect(mockHandleMessageStream).not.toHaveBeenCalled();
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
      await expect(consumeStream(response, 'hello', state, actions, abortController, false, '')).rejects.toThrow(
        'Service response timeout',
      );

      expect(mockRecoverPendingApprovals).toHaveBeenCalledTimes(1);
    } finally {
      nowSpy.mockRestore();
    }
  });

  describe('when the user stops the turn', () => {
    function armStreamHandlers(): void {
      mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'm-stop', data: 'hi' });
      mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'hi' });
    }

    it('never starts reading for a turn that was already stopped, and raises a genuine AbortError', async () => {
      const state = createBaseState();
      const abortController = new AbortController();
      abortController.abort();
      armStreamHandlers();
      // A stream without data would keep a started read waiting for good: no abort event fires for a signal that is
      // already aborted.
      const response = new Response(new ReadableStream<Uint8Array>({ start: () => undefined }), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      });

      const run = observe(consumeStream(response, 'hello', state, createActions(state), abortController, false, ''));
      await eventually(() => expect(run.isSettled()).toBe(true));

      expect(run.error()).toMatchObject({ name: 'AbortError' });
      expect(mockHandleMessageStream).not.toHaveBeenCalled();
    });

    it('ends a pending read at once and leaves no watchdog heal behind', async () => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      const onCancel = vi.fn();
      const state = createBaseState();
      const actions = createActions(state);
      const abortController = new AbortController();
      armStreamHandlers();

      const run = observe(
        consumeStream(createSilentResponse(onCancel), 'hello', state, actions, abortController, false, ''),
      );
      // The first event arms the silence watchdog; the consumer then waits for the next one.
      await eventually(() => expect(mockHandleMessageStream).toHaveBeenCalledTimes(1));

      abortController.abort();
      // Far below the 3.5 s silence threshold: only the stop itself can end the consumer this early.
      await vi.advanceTimersByTimeAsync(100);

      expect(run.isSettled()).toBe(true);
      expect(run.error()).toMatchObject({ name: 'AbortError' });
      expect(onCancel).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(10_000);
      expect(actions.setLoading).not.toHaveBeenCalled();
      expect(actions._processSuggestions).not.toHaveBeenCalled();
    });

    it('reports a read that failed because of the stop as the stop itself, not as an interrupted stream', async () => {
      const state = createBaseState();
      const abortController = new AbortController();
      armStreamHandlers();

      const run = observe(
        consumeStream(
          createAbortFailingResponse(abortController.signal),
          'hello',
          state,
          createActions(state),
          abortController,
          false,
          '',
        ),
      );
      await eventually(() => expect(mockHandleMessageStream).toHaveBeenCalledTimes(1));

      abortController.abort();
      await eventually(() => expect(run.isSettled()).toBe(true));

      expect(run.error()).toMatchObject({ name: 'AbortError' });
    });

    it('detaches its abort listener once the stream has been consumed', async () => {
      const state = createBaseState();
      const abortController = new AbortController();
      const detach = vi.spyOn(abortController.signal, 'removeEventListener');
      armStreamHandlers();
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

      try {
        await consumeStream(
          createSseResponse(STOP_TEST_EVENT),
          'hello',
          state,
          createActions(state),
          abortController,
          false,
          '',
        );
      } finally {
        warnSpy.mockRestore();
      }

      expect(detach).toHaveBeenCalledWith('abort', expect.any(Function));
    });

    it('does not re-attach to a stream whose read failed because of the stop', async () => {
      const state = createBaseState({ chatId: 'chat-stop-attach', actionMode: 'agent' });
      const abortController = new AbortController();
      mockCreateMessageRequest.mockResolvedValue(createAbortFailingResponse(abortController.signal));
      armStreamHandlers();

      const run = observe(
        executeStreamWithRetry(
          'hello',
          'msg-stop-attach',
          state,
          createActions(state),
          null,
          abortController,
          false,
          '',
        ),
      );
      await eventually(() => expect(mockHandleMessageStream).toHaveBeenCalledTimes(1));

      abortController.abort();
      await eventually(() => expect(run.isSettled()).toBe(true));

      expect(run.error()).toMatchObject({ name: 'AbortError' });
      expect(mockAttachToChat).not.toHaveBeenCalled();
    });

    it('ends the wait before a request retry as soon as the turn is stopped', async () => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      const state = createBaseState();
      const abortController = new AbortController();
      mockCreateMessageRequest.mockResolvedValue(new Response('temporary', { status: 503 }));

      try {
        const run = observe(
          executeStreamWithRetry(
            'hello',
            'msg-stop-retry',
            state,
            createActions(state),
            null,
            abortController,
            false,
            '',
          ),
        );
        // The first attempt failed transiently and the loop is backing off before the next one.
        await eventually(() => expect(vi.getTimerCount()).toBe(1));

        abortController.abort();
        // The backoff lasts at least 1.6 s: only the stop can end the turn this early.
        await vi.advanceTimersByTimeAsync(100);

        expect(run.isSettled()).toBe(true);
        expect(run.error()).toMatchObject({ name: 'AbortError' });
        expect(mockCreateMessageRequest).toHaveBeenCalledTimes(1);
        expect(vi.getTimerCount()).toBe(0);
      } finally {
        warnSpy.mockRestore();
      }
    });

    it('ends the wait before an attach retry as soon as the turn is stopped', async () => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
      const state = createBaseState({ chatId: 'chat-stop-attach-wait', actionMode: 'agent' });
      const abortController = new AbortController();
      mockCreateMessageRequest.mockResolvedValue(createInterruptedResponse(STOP_TEST_EVENT));
      armStreamHandlers();
      mockAttachToChat.mockRejectedValue(new Error('attach network down'));

      try {
        const run = observe(
          executeStreamWithRetry(
            'hello',
            'msg-stop-attach-wait',
            state,
            createActions(state),
            null,
            abortController,
            false,
            '',
          ),
        );
        // The interrupted stream's first re-attach failed and the loop is backing off before the next one.
        await eventually(() => expect(vi.getTimerCount()).toBe(1));

        abortController.abort();
        await vi.advanceTimersByTimeAsync(100);

        expect(run.isSettled()).toBe(true);
        expect(run.error()).toMatchObject({ name: 'AbortError' });
        expect(mockAttachToChat).toHaveBeenCalledTimes(1);
        expect(vi.getTimerCount()).toBe(0);
      } finally {
        warnSpy.mockRestore();
        errorSpy.mockRestore();
      }
    });

    it.each([
      ['gives up', { ok: false, err: 'workspace-stream-ready-timeout' }],
      ['comes up', { ok: true }],
    ])(
      'ends quietly and posts nothing when the stop arrives before the workspace stream %s',
      async (_outcome, gateResult) => {
        (window as Window & { __MYRM_E2E_DIRECT_SSE__?: boolean }).__MYRM_E2E_DIRECT_SSE__ = false;
        const state = createBaseState();
        const abortController = new AbortController();
        let settleGate: (result: { ok: boolean; err?: string }) => void = () => undefined;
        mockWaitUntilReady.mockReturnValue(
          new Promise((resolve) => {
            settleGate = resolve;
          }),
        );

        const run = observe(
          executeStreamWithRetry(
            'hello',
            'msg-stop-gate',
            state,
            createActions(state),
            null,
            abortController,
            false,
            '',
          ),
        );
        await eventually(() => expect(mockWaitUntilReady).toHaveBeenCalledTimes(1));

        abortController.abort();
        // The gate cannot be interrupted; its verdict only arrives after the stop.
        settleGate(gateResult);
        await eventually(() => expect(run.isSettled()).toBe(true));

        expect(run.error()).toMatchObject({ name: 'AbortError' });
        expect(mockCreateMessageRequest).not.toHaveBeenCalled();
      },
    );
  });
});
