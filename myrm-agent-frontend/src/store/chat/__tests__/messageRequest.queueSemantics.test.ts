/**
 * Send-lifecycle contract the message queue relies on:
 * - `sendMessage` reports whether the request was dispatched,
 * - a busy refusal retracts the optimistic user bubble (the caller requeues the message),
 * - a server refusal (non-retryable HTTP error) reports the turn as not dispatched so the caller keeps the message,
 *   while a failure after the server took the turn still counts as dispatched,
 * - a queued message sends its own attachments and leaves the composer's live attachments alone,
 * - a refusal before the request lifecycle starts leaves the composer attachments in place, one inside it empties
 *   them: the composer restores its draft from exactly that difference.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchWithTimeout } from '@/lib/api';
import { createAISearchStream } from '@/services/chat';
import { setGlobalTranslator, showI18nToast } from '@/services/i18nToastService';
import { sendMessage, type ChatActionsMethods, type ChatActionsState } from '@/store/chat/messageRequest';
import { isHeldByOtherTurn, resolveRequestState, retractUserBubble } from '@/store/chat/sendLifecycle';
import { AgentBusyError } from '@/store/chat/streamConsumer';
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

const CHAT_ID = 'chat-queue-semantics';

// An archive extension keeps the multimodal builder from fetching the attachment content.
function makeFile(id: string): ChatFile {
  return { id, fileName: `${id}.zip`, fileExtension: 'zip', fileType: 'uploaded', fileUrl: `https://files.test/${id}` };
}

function userBubble(messageId: string, role: Message['role'] = 'user'): Message {
  return { content: 'hello', messageId, chatId: CHAT_ID, role, createdAt: new Date() } as Message;
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

describe('sendLifecycle helpers', () => {
  it('retractUserBubble removes only the trailing user bubble of the request', () => {
    const state = { messages: [userBubble('older'), userBubble('req-1')] } as ChatState;
    retractUserBubble('req-1')(state);
    expect(state.messages.map((m) => m.messageId)).toEqual(['older']);
  });

  it('retractUserBubble leaves a same-id assistant message and other requests untouched', () => {
    const assistantState = { messages: [userBubble('req-1'), userBubble('req-1', 'assistant')] } as ChatState;
    retractUserBubble('req-1')(assistantState);
    expect(assistantState.messages).toHaveLength(2);

    const otherState = { messages: [userBubble('req-2')] } as ChatState;
    retractUserBubble('req-1')(otherState);
    expect(otherState.messages).toHaveLength(1);
  });

  it('resolveRequestState keeps the original state when nothing overrides it', () => {
    const state = { agentConfig: null, files: [makeFile('live')], cameraFrames: ['frame'] };
    expect(resolveRequestState(state, undefined, undefined)).toBe(state);
  });

  it('resolveRequestState swaps in the queued attachments and drops live camera frames', () => {
    const state = { agentConfig: null, files: [makeFile('live')], cameraFrames: ['frame'] };
    const queued = { files: [makeFile('queued')] };
    const resolved = resolveRequestState(state, undefined, queued);
    expect(resolved.files).toEqual(queued.files);
    expect(resolved.cameraFrames).toEqual([]);
    expect(state.files.map((f) => f.id)).toEqual(['live']);
  });

  it('isHeldByOtherTurn is true for the live controller of another turn only', () => {
    const own = new AbortController();
    expect(isHeldByOtherTurn(new AbortController(), own)).toBe(true);
    expect(isHeldByOtherTurn(own, own)).toBe(false);
  });

  it('isHeldByOtherTurn treats a missing, cleared or serialized handle as held by nobody', () => {
    const own = new AbortController();
    expect(isHeldByOtherTurn(null, own)).toBe(false);
    expect(isHeldByOtherTurn(undefined, own)).toBe(false);
    // A pane snapshot is a JSON clone, so its handle is a plain object rather than a live controller.
    expect(isHeldByOtherTurn(JSON.parse(JSON.stringify(new AbortController())), own)).toBe(false);
  });
});

describe('sendMessage queue semantics', () => {
  let store: ChatActionsState & { messages: Message[] };
  const pushedBubbleFiles: Array<ChatFile[] | undefined> = [];

  const buildActions = (): ChatActionsMethods =>
    ({
      setMessages: vi.fn((updater: (draft: ChatState) => void) => {
        updater(store as unknown as ChatState);
        const bubble = store.messages[store.messages.length - 1];
        if (bubble?.role === 'user') {
          pushedBubbleFiles.push(bubble.files as ChatFile[] | undefined);
        }
      }),
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

  const send = (
    options: { queued?: { files: ChatFile[] }; loading?: boolean; requestId?: string } = {},
    actions: ChatActionsMethods = buildActions(),
  ) =>
    sendMessage(
      'hello',
      options.requestId ?? 'req-1',
      { ...store, loading: options.loading ?? false },
      actions,
      () => 'req-1',
      () => 'req-1',
      undefined,
      undefined,
      undefined,
      false,
      undefined,
      options.queued,
    );

  beforeEach(() => {
    window.__MYRM_E2E_DIRECT_SSE__ = true;
    setGlobalTranslator((key: string) => key);
    useToolApprovalStore.getState().clearAll();
    vi.mocked(showI18nToast).mockClear();
    pushedBubbleFiles.length = 0;

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
  });

  const refuseAsBusy = () => vi.mocked(createAISearchStream).mockResolvedValue(new Response('busy', { status: 409 }));

  it('resolves false without touching the transcript when the chat is still loading', async () => {
    await expect(send({ loading: true })).resolves.toBe(false);
    expect(store.messages).toHaveLength(0);
    expect(createAISearchStream).not.toHaveBeenCalled();
  });

  it('rejects with AgentBusyError and leaves no ghost bubble when the server is busy', async () => {
    refuseAsBusy();
    await expect(send()).rejects.toBeInstanceOf(AgentBusyError);

    expect(pushedBubbleFiles).toHaveLength(1);
    expect(store.messages).toHaveLength(0);
  });

  it('resolves true once the request was dispatched, even when it then fails visibly', async () => {
    vi.mocked(createAISearchStream).mockRejectedValue(new Error('invalid request'));

    await expect(send()).resolves.toBe(true);

    expect(createAISearchStream).toHaveBeenCalledTimes(1);
  });

  it.each([400, 401, 403, 404, 413, 422, 500])(
    'resolves false and leaves no ghost bubble when the server refuses the turn with HTTP %i',
    async (status) => {
      vi.mocked(createAISearchStream).mockResolvedValue(
        new Response(JSON.stringify({ detail: 'refused' }), { status }),
      );

      await expect(send()).resolves.toBe(false);

      expect(createAISearchStream).toHaveBeenCalledTimes(1);
      expect(store.messages).toHaveLength(0);
      expect(showI18nToast).toHaveBeenCalledTimes(1);
    },
  );

  it('resolves true when the server took the turn and only the re-attach after a dropped stream is refused', async () => {
    vi.mocked(createAISearchStream).mockResolvedValue(droppedStream());
    vi.mocked(fetchWithTimeout).mockResolvedValueOnce(new Response('denied', { status: 500 }));

    await expect(send()).resolves.toBe(true);

    expect(createAISearchStream).toHaveBeenCalledTimes(1);
    expect(fetchWithTimeout).toHaveBeenCalledWith(`/agents/chat/${CHAT_ID}/attach`, expect.anything(), 0);
  });

  it('clears the live attachments after a direct send', async () => {
    refuseAsBusy();

    await expect(send()).rejects.toBeInstanceOf(AgentBusyError);

    expect(store.files).toEqual([]);
  });

  it('sends the queued attachments and keeps the live composer attachments', async () => {
    refuseAsBusy();
    const queuedFiles = [makeFile('queued-a'), makeFile('queued-b')];

    await expect(send({ queued: { files: queuedFiles } })).rejects.toBeInstanceOf(AgentBusyError);

    const requestBody = vi.mocked(createAISearchStream).mock.calls[0]?.[0] as { uploaded_file_ids?: string[] };
    expect(requestBody.uploaded_file_ids).toEqual(['queued-a', 'queued-b']);
    expect(pushedBubbleFiles[0]?.map((file) => file.id)).toEqual(['queued-a', 'queued-b']);
    expect(store.files.map((file) => file.id)).toEqual(['live']);
  });

  it('tells the user to wait, with a localized notice, when the chat is still loading', async () => {
    await expect(send({ loading: true })).resolves.toBe(false);

    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.sendBlocked.title',
      undefined,
      expect.objectContaining({ descriptionKey: 'chat.sendBlocked.busyDescription' }),
    );
  });

  // The composer restores its draft after a refusal; what is left in the store differs by refusal path.
  describe('what a refusal leaves in the composer', () => {
    const attachmentIds = () => store.files.map((file) => file.id);

    it('keeps the attachments and never resets the attachment list when the chat is still loading', async () => {
      const actions = buildActions();

      await expect(send({ loading: true }, actions)).resolves.toBe(false);

      expect(attachmentIds()).toEqual(['live']);
      expect(actions.setHideAttachList).not.toHaveBeenCalled();
    });

    it('keeps the attachments and never resets the attachment list when there is no chat yet', async () => {
      const actions = buildActions();
      (store as unknown as { chatId: string }).chatId = '';

      await expect(send({}, actions)).resolves.toBe(false);

      expect(attachmentIds()).toEqual(['live']);
      expect(actions.setHideAttachList).not.toHaveBeenCalled();
    });

    it('empties the attachments and shows the attachment list again when the model configuration is invalid', async () => {
      const actions = buildActions();
      useProviderStore.setState({ providers: [] });

      await expect(send({}, actions)).resolves.toBe(false);

      expect(attachmentIds()).toEqual([]);
      expect(actions.setHideAttachList).toHaveBeenCalledWith(false);
    });

    it('empties the attachments and shows the attachment list again when the server refuses the turn', async () => {
      const actions = buildActions();
      vi.mocked(createAISearchStream).mockResolvedValue(
        new Response(JSON.stringify({ detail: 'too large' }), { status: 413 }),
      );

      await expect(send({}, actions)).resolves.toBe(false);

      expect(attachmentIds()).toEqual([]);
      expect(actions.setHideAttachList).toHaveBeenCalledWith(false);
    });
  });
});
