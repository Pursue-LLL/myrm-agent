/**
 * What a failed turn leaves behind, through the real request pipeline (only the network and the workspace
 * stream readiness are replaced).
 *
 * A resume answers a card that already sits in the transcript, so a failure never edits the transcript: it
 * resolves `false` when the server never took the answer (refused, no reply after every retry, workspace stream
 * not ready) and the caller that rolls its card back reports it. A fresh send keeps its optimistic bubble only
 * while a retry can still deliver it.
 *
 * The failure toast shows the server's own explanation when it gave a structured one, a fixed localized line
 * otherwise; the raw error goes to the console.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchWithTimeout } from '@/lib/api';
import { createAISearchStream } from '@/services/chat';
import { connectionManager } from '@/services/ConnectionManager';
import { setGlobalTranslator, showI18nToast } from '@/services/i18nToastService';
import { sendMessage, type ChatActionsMethods, type ChatActionsState } from '@/store/chat/messageRequest';
import { AgentBusyError, ApprovalExpiredError } from '@/store/chat/streamErrors';
import type { ChatState, File as ChatFile, Message } from '@/store/chat/types';
import { getInitialDefaultModelConfig } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';

vi.mock('@/services/chat', () => ({
  createAISearchStream: vi.fn(),
}));

vi.mock('@/services/i18nToastService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/i18nToastService')>();
  return { ...actual, showI18nToast: vi.fn() };
});

// Spied pass-through: only the re-attach request of the interrupted-stream case is answered by the test.
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, fetchWithTimeout: vi.fn(actual.fetchWithTimeout) };
});

// The E2E-only attach probe polls the health endpoint; it has no place in a unit test.
vi.mock('@/store/chat/streamConsumer', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/store/chat/streamConsumer')>();
  return {
    ...actual,
    tryE2eAttachForPendingApproval: vi.fn(async () => ({ attached: false, queueLen: 0, attempt: 0 })),
  };
});

const CHAT_ID = 'chat-send-failure';
const REQUEST_ID = 'r-1';
// One initial attempt plus ten retries.
const ATTEMPTS_UNTIL_GIVING_UP = 11;
const SERVER_DETAIL =
  'Request exceeds gateway token limits (approx 120K tokens). Please reduce the size of your input.';

function makeFile(id: string): ChatFile {
  return { id, fileName: `${id}.zip`, fileExtension: 'zip', fileType: 'uploaded', fileUrl: `https://files.test/${id}` };
}

function message(role: Message['role'], content: string): Message {
  return { content, messageId: REQUEST_ID, chatId: CHAT_ID, role, createdAt: new Date() } as Message;
}

/** A reply that delivers a keepalive and then drops, which makes the client re-attach to the running turn. */
function droppedStream(): Response {
  let delivered = false;
  return new Response(
    new ReadableStream<Uint8Array>({
      pull(controller) {
        if (delivered) {
          controller.error(new TypeError('network error'));
          return;
        }
        delivered = true;
        controller.enqueue(new TextEncoder().encode('event: heartbeat\ndata: null\n\n'));
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
}

const refusedWith = (status: number, body: string) =>
  vi.mocked(createAISearchStream).mockResolvedValue(new Response(body, { status }));

/** The production busy refusal: HTTP 200 whose event stream carries one AgentBusyError frame. */
const busyResponse = (): Response =>
  new Response(
    `data: ${JSON.stringify({
      type: 'error',
      error_type: 'AgentBusyError',
      status_code: 409,
      messageId: REQUEST_ID,
      data: 'Agent is busy processing another request for this session.',
    })}\n\n`,
    { headers: { 'Content-Type': 'text/event-stream' } },
  );

/** The production risk refusal: HTTP 200 whose event stream carries one `risk_blocked` frame naming the rules. */
const riskBlockedResponse = (): Response =>
  new Response(
    `data: ${JSON.stringify({
      type: 'risk_blocked',
      data: { rules: [{ rule_id: 'api_key_like', display_name: 'API key', severity: 'high' }] },
    })}\n\n`,
    { headers: { 'Content-Type': 'text/event-stream' } },
  );

const RISK_NOTICE_KEY = 'settings.securityPolicy.riskRules.blockedTitle';

/** Runs a request that waits between retries on a fake clock until it settles. */
async function runWithRetries<T>(start: () => Promise<T>): Promise<T> {
  vi.useFakeTimers();
  try {
    const request = start();
    let settled = false;
    void request.then(
      () => {
        settled = true;
      },
      () => {
        settled = true;
      },
    );
    for (let step = 0; step < 400 && !settled; step += 1) {
      await vi.advanceTimersByTimeAsync(5_000);
    }
    return await request;
  } finally {
    vi.useRealTimers();
  }
}

describe('sendMessage failure handling', () => {
  let store: ChatActionsState & { messages: Message[] };

  const buildActions = (): ChatActionsMethods =>
    ({
      setMessages: vi.fn((updater: (draft: ChatState) => void) => updater(store as unknown as ChatState)),
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
      setHideAttachList: vi.fn(),
      setHasUsedImagesInCurrentChat: vi.fn(),
      setSelectedModels: vi.fn(),
      setHasUserSelectedModel: vi.fn(),
      clearCurrentSessionMessageId: vi.fn(),
      clearPendingWorkflowTemplate: vi.fn(),
      _processSuggestions: vi.fn(),
      scheduleAutoSave: vi.fn(),
      setInputMessage: vi.fn(),
    }) as unknown as ChatActionsMethods;

  const request = (input: string, resumeValue?: unknown) =>
    sendMessage(
      input,
      REQUEST_ID,
      { ...store, loading: false },
      buildActions(),
      () => REQUEST_ID,
      () => REQUEST_ID,
      resumeValue,
    );
  const send = () => request('hello');
  const resume = () => request('', { action: 'approve' });

  const transcript = () =>
    store.messages.map((entry) => `${entry.role}:${entry.messageId}${entry.sendFailed ? ':failed' : ''}`);
  const toastOptions = () => vi.mocked(showI18nToast).mock.calls[0]?.[2];

  const answeredCard = () => {
    store.messages = [message('user', 'deploy it'), message('assistant', 'approval card')];
  };

  beforeEach(() => {
    window.__MYRM_E2E_DIRECT_SSE__ = true;
    setGlobalTranslator((key: string) => key);
    useToolApprovalStore.getState().clearAll();
    vi.mocked(showI18nToast).mockClear();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    useProviderStore.setState({
      providers: [
        {
          id: 'minimax',
          name: 'MiniMax',
          isBuiltIn: true,
          isEnabled: true,
          apiKeys: [{ id: 'k1', key: 'sk-test', remark: 'default', isActive: true }],
          apiUrl: 'https://api.example.com/v1',
          enabledModels: ['MiniMax-M2'],
          availableModels: ['MiniMax-M2'],
          routingProfile: 'minimax',
        },
      ],
      defaultModelConfig: {
        ...getInitialDefaultModelConfig(),
        baseModel: {
          ...getInitialDefaultModelConfig().baseModel,
          primary: { providerId: 'minimax', model: 'MiniMax-M2' },
        },
      },
    });

    store = {
      chatId: CHAT_ID,
      actionMode: 'agent',
      searchDepth: 'normal',
      agentConfig: null,
      abortController: null,
      loading: false,
      loadingOlder: false,
      messages: [],
      files: [makeFile('live')],
      mentionReferences: [],
      cameraFrames: [],
      hideAttachList: false,
      currentSessionMessageId: null,
      currentBuiltinTools: ['web_search', 'memory'],
      incognitoMode: false,
      clearMentionReferences: vi.fn(),
      removeMentionReferencesByTypes: vi.fn(),
    } as unknown as ChatActionsState & { messages: Message[] };

    vi.mocked(createAISearchStream).mockReset();
  });

  afterEach(() => {
    delete window.__MYRM_E2E_DIRECT_SSE__;
    vi.restoreAllMocks();
  });

  const networkDown = () => vi.mocked(createAISearchStream).mockRejectedValue(new TypeError('Failed to fetch'));
  const gateFails = (err: string) =>
    vi.spyOn(connectionManager, 'waitUntilReady').mockResolvedValue({ ok: false, err });
  const useMultiplexedStream = () => {
    delete window.__MYRM_E2E_DIRECT_SSE__;
  };

  describe('a resume, whose answered card is already in the transcript', () => {
    beforeEach(answeredCard);

    it('stays undelivered and leaves the transcript alone when no request got an answer', async () => {
      networkDown();

      await expect(runWithRetries(resume)).resolves.toBe(false);

      expect(createAISearchStream).toHaveBeenCalledTimes(ATTEMPTS_UNTIL_GIVING_UP);
      expect(transcript()).toEqual([`user:${REQUEST_ID}`, `assistant:${REQUEST_ID}`]);
    });

    it('stays undelivered and leaves the transcript alone when the server refuses it', async () => {
      refusedWith(401, JSON.stringify({ detail: 'Session expired' }));

      await expect(resume()).resolves.toBe(false);

      expect(createAISearchStream).toHaveBeenCalledTimes(1);
      expect(transcript()).toEqual([`user:${REQUEST_ID}`, `assistant:${REQUEST_ID}`]);
    });

    it('stays undelivered and leaves the transcript alone when the workspace stream is not ready', async () => {
      useMultiplexedStream();
      gateFails('workspace-stream-ready-timeout');

      await expect(resume()).resolves.toBe(false);

      expect(createAISearchStream).not.toHaveBeenCalled();
      expect(transcript()).toEqual([`user:${REQUEST_ID}`, `assistant:${REQUEST_ID}`]);
    });

    it('leaves the reporting of an undelivered answer to the caller that rolls its card back', async () => {
      refusedWith(401, JSON.stringify({ detail: 'Session expired' }));

      await resume();

      expect(showI18nToast).not.toHaveBeenCalled();
    });

    it('counts as delivered, with one notice and an untouched transcript, once the server took it', async () => {
      vi.mocked(createAISearchStream).mockResolvedValue(droppedStream());
      vi.mocked(fetchWithTimeout).mockResolvedValueOnce(new Response('denied', { status: 500 }));

      await expect(resume()).resolves.toBe(true);

      expect(transcript()).toEqual([`user:${REQUEST_ID}`, `assistant:${REQUEST_ID}`]);
      expect(showI18nToast).toHaveBeenCalledTimes(1);
      expect(toastOptions()).toMatchObject({ descriptionKey: 'chat.messageFailed.generic' });
    });

    it('rejects with AgentBusyError and leaves the transcript alone when the server is busy', async () => {
      vi.mocked(createAISearchStream).mockResolvedValue(busyResponse());

      await expect(resume()).rejects.toBeInstanceOf(AgentBusyError);

      expect(transcript()).toEqual([`user:${REQUEST_ID}`, `assistant:${REQUEST_ID}`]);
    });

    it('stays undelivered, with the one risk notice, when a risk rule holds the answer', async () => {
      vi.mocked(createAISearchStream).mockResolvedValue(riskBlockedResponse());

      await expect(resume()).resolves.toBe(false);

      expect(createAISearchStream).toHaveBeenCalledTimes(1);
      expect(transcript()).toEqual([`user:${REQUEST_ID}`, `assistant:${REQUEST_ID}`]);
      expect(vi.mocked(showI18nToast).mock.calls.map(([key]) => key)).toEqual([RISK_NOTICE_KEY]);
    });

    it('rejects with ApprovalExpiredError, quietly and without a retry, when the timeout already resolved the interrupt', async () => {
      refusedWith(409, '{}');

      await expect(resume()).rejects.toBeInstanceOf(ApprovalExpiredError);

      expect(createAISearchStream).toHaveBeenCalledTimes(1);
      expect(transcript()).toEqual([`user:${REQUEST_ID}`, `assistant:${REQUEST_ID}`]);
      expect(showI18nToast).not.toHaveBeenCalled();
    });
  });

  describe('a fresh send', () => {
    it('is undelivered and retracts its bubble when the workspace stream is not ready before the first request', async () => {
      useMultiplexedStream();
      gateFails('workspace-stream-ready-timeout');

      await expect(send()).resolves.toBe(false);

      expect(createAISearchStream).not.toHaveBeenCalled();
      expect(transcript()).toEqual([]);
      expect(showI18nToast).toHaveBeenCalledTimes(1);
    });

    it('is undelivered and retracts its bubble, with the one risk notice and no retry, when a risk rule holds the text', async () => {
      vi.mocked(createAISearchStream).mockResolvedValue(riskBlockedResponse());

      await expect(send()).resolves.toBe(false);

      expect(createAISearchStream).toHaveBeenCalledTimes(1);
      expect(transcript()).toEqual([]);
      expect(vi.mocked(showI18nToast).mock.calls.map(([key]) => key)).toEqual([RISK_NOTICE_KEY]);
    });

    it('keeps retrying a workspace stream failure that looks like a dropped connection', async () => {
      useMultiplexedStream();
      const gate = gateFails('Failed to fetch');

      await expect(runWithRetries(send)).resolves.toBe(true);

      expect(gate).toHaveBeenCalledTimes(ATTEMPTS_UNTIL_GIVING_UP);
      expect(createAISearchStream).not.toHaveBeenCalled();
      expect(transcript()).toEqual([`user:${REQUEST_ID}:failed`]);
    });

    it('stays an ordinary failure when the stream is not ready after a request already went out', async () => {
      useMultiplexedStream();
      vi.spyOn(connectionManager, 'waitUntilReady')
        .mockResolvedValueOnce({ ok: true })
        .mockResolvedValue({ ok: false, err: 'workspace-stream-ready-timeout' });
      networkDown();

      await expect(runWithRetries(send)).resolves.toBe(true);

      expect(createAISearchStream).toHaveBeenCalledTimes(1);
      expect(transcript()).toEqual([]);
    });

    it('keeps its bubble, marked failed, once every retry went unanswered', async () => {
      networkDown();

      await expect(runWithRetries(send)).resolves.toBe(true);

      expect(createAISearchStream).toHaveBeenCalledTimes(ATTEMPTS_UNTIL_GIVING_UP);
      expect(transcript()).toEqual([`user:${REQUEST_ID}:failed`]);
      expect(toastOptions()).toMatchObject({ descriptionKey: 'chat.messageFailed.networkError' });
    });

    it('shows the server explanation when a refusal carries a structured one', async () => {
      refusedWith(400, JSON.stringify({ detail: SERVER_DETAIL }));

      await expect(send()).resolves.toBe(false);

      expect(toastOptions()).toMatchObject({
        descriptionKey: 'chat.messageFailed.description',
        descriptionValues: { error: SERVER_DETAIL },
      });
    });

    it('never shows an unstructured refusal body, such as a proxy error page', async () => {
      refusedWith(500, '<html><body>502 Bad Gateway nginx/1.25</body></html>');

      await expect(send()).resolves.toBe(false);

      expect(toastOptions()).toMatchObject({ descriptionKey: 'chat.messageFailed.generic' });
      expect(toastOptions()).not.toHaveProperty('descriptionValues');
    });

    it('never shows an internal error text and keeps it in the console', async () => {
      const failure = new Error('internal: reducer exploded');
      vi.mocked(createAISearchStream).mockRejectedValue(failure);

      await expect(send()).resolves.toBe(true);

      expect(toastOptions()).toMatchObject({ descriptionKey: 'chat.messageFailed.generic' });
      expect(toastOptions()).not.toHaveProperty('descriptionValues');
      expect(console.error).toHaveBeenCalledWith(expect.any(String), failure);
    });
  });
});
