/**
 * The stream consumer's resilience paths: refused and busy answers, request retries, wiki-metric bookkeeping,
 * attach recovery after an interrupted read, and the E2E attach fallback.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  approvalState,
  createActions,
  createBaseState,
  createInterruptedResponse,
  createSseResponse,
  eventually,
  installStreamConsumerLifecycle,
  mockAttachForHitlRecovery,
  mockAttachToChat,
  mockClearPendingWorkflowTemplate,
  mockConsumePendingChatWikiQuerySuccess,
  mockCreateMessageRequest,
  mockDecryptSseFrame,
  mockHandleMessageStream,
  mockLoadMessages,
  mockLoadStoredE2EESession,
  mockParseSseEnvelope,
  mockRecordWikiQuerySubmitted,
  mockRecoverPendingApprovals,
  mockReleaseTurnInspectorControls,
  mockResolveChatWikiEvidenceContext,
  mockResolveE2eApiBase,
} from './streamConsumerTestKit';
import { consumeStream } from '../consumeStream';
import { executeStreamWithRetry } from '../streamConsumer';
import { AgentBusyError, ApprovalAlreadyResolvedError, RequestRefusedError } from '../streamErrors';
import { FatalNetworkError } from '@/lib/utils/networkResilience';
import type { Message } from '@/store/chat/types';

describe('streamConsumer resilience paths', () => {
  installStreamConsumerLifecycle();

  it('throws ApprovalAlreadyResolvedError without retrying when a resume hits an interrupt someone else already resolved (HTTP 409)', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(new Response('{}', { status: 409 }));

    await expect(
      executeStreamWithRetry('', 'msg-1', state, actions, null, abortController, false, '', { granted: false }),
    ).rejects.toBeInstanceOf(ApprovalAlreadyResolvedError);

    expect(mockCreateMessageRequest).toHaveBeenCalledTimes(1);
  });

  it('refuses a non-resume turn answered with HTTP 409 instead of calling the chat busy', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(new Response('conflict', { status: 409 }));

    const failure = executeStreamWithRetry('hello', 'msg-1', state, actions, null, abortController, false, '');

    await expect(failure).rejects.toBeInstanceOf(RequestRefusedError);
    await expect(failure).rejects.not.toBeInstanceOf(AgentBusyError);
    expect(mockCreateMessageRequest).toHaveBeenCalledTimes(1);
  });

  it('keeps pending workflow template armed when agent-stream POST fails', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(new Response('refused', { status: 400 }));

    await expect(
      executeStreamWithRetry('hello', 'msg-template-armed', state, actions, null, abortController, false, ''),
    ).rejects.toBeInstanceOf(RequestRefusedError);

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

  it('throws AgentBusyError when the direct SSE body carries a busy envelope', async () => {
    const state = createBaseState({ chatId: 'chat-busy-body', actionMode: 'agent' });
    const actions = createActions(state);
    const abortController = new AbortController();
    const busyEvent = {
      type: 'error',
      error_type: 'AgentBusyError',
      status_code: 409,
      messageId: 'msg-busy-body',
      data: 'Agent is busy processing another request for this session.',
    };
    mockResolveE2eApiBase.mockReturnValue(null);
    mockCreateMessageRequest.mockResolvedValue(createSseResponse(`data: ${JSON.stringify(busyEvent)}\n\n`));
    mockParseSseEnvelope.mockReturnValue(busyEvent);

    await expect(
      executeStreamWithRetry('hello', 'msg-busy-body', state, actions, null, abortController, false, ''),
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

  it('runs the E2E attach fallback inside an E2E-bound runtime', async () => {
    mockResolveE2eApiBase.mockReturnValue('http://127.0.0.1:8100');
    const state = createBaseState({ chatId: 'chat-e2e-attach' });
    const actions = createActions(state);
    mockAttachForHitlRecovery.mockResolvedValue({ attached: true, queueLen: 0, source: 'e2e' });
    mockCreateMessageRequest.mockResolvedValue(
      createSseResponse('data: {"type":"message","messageId":"m-e2e","data":"ok"}\n\n'),
    );

    try {
      await executeStreamWithRetry('hello', 'msg-e2e', state, actions, null, new AbortController(), false, '');
      expect(window.__MYRM_E2E_ATTACH_DIAG__?.attached).toBe(true);
    } finally {
      delete window.__MYRM_E2E_ATTACH_DIAG__;
    }
  });

  it('skips the E2E attach fallback outside an E2E-bound runtime', async () => {
    const state = createBaseState({ chatId: 'chat-plain' });
    const actions = createActions(state);
    mockCreateMessageRequest.mockResolvedValue(
      createSseResponse('data: {"type":"message","messageId":"m-plain","data":"ok"}\n\n'),
    );

    await executeStreamWithRetry('hello', 'msg-plain', state, actions, null, new AbortController(), false, '');

    expect(mockAttachForHitlRecovery).not.toHaveBeenCalled();
    expect(window.__MYRM_E2E_ATTACH_DIAG__).toBeUndefined();
  });
});
