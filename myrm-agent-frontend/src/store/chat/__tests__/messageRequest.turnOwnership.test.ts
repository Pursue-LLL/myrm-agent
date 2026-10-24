/**
 * Which turn may release the shared turn state (loading flag, abort handle, request id, composer attachments and
 * their hidden attach list), through the real chat store and request pipeline (only the network is replaced).
 *
 * A turn ends after its stream did: it reconciles the transcript with the server first. The next turn can start
 * inside that gap, and the ended turn must then leave the shared state alone: resetting it would leave the running
 * turn without a Stop button. A stopped turn ends at once wherever it waits (for a stream event, before a retry), so
 * nothing of it can reach into the next turn later.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchWithTimeout } from '@/lib/api';
import { cancelActiveChatAgent, cancelAgentRequest, createAISearchStream } from '@/services/chat';
import { connectionManager } from '@/services/ConnectionManager';
import { showI18nToast } from '@/services/i18nToastService';
import { attachToChat, type ChatActionsMethods } from '@/store/chat/messageRequest';
import type { File as ChatFile } from '@/store/chat/types';
import { getInitialDefaultModelConfig } from '@/store/config/providerTypes';
import useChatStore from '@/store/useChatStore';
import useProviderStore from '@/store/useProviderStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import useWorkspaceStore, { type PaneConfig } from '@/store/useWorkspaceStore';

const reconcile = vi.hoisted(() => ({ hold: false, waiting: [] as Array<() => void> }));

vi.mock('@/services/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/chat')>();
  return {
    ...actual,
    createAISearchStream: vi.fn(),
    cancelAgentRequest: vi.fn().mockResolvedValue(undefined),
    cancelActiveChatAgent: vi.fn().mockResolvedValue(undefined),
    // The server reconcile that ends a turn; a test holds it to keep the turn from finishing.
    getChatDetail: vi.fn(() => {
      const detail = { chat: { agent_id: null, workspace_dir: null } };
      return reconcile.hold
        ? new Promise((resolve) => reconcile.waiting.push(() => resolve(detail)))
        : Promise.resolve(detail);
    }),
  };
});

vi.mock('@/services/i18nToastService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/i18nToastService')>();
  return { ...actual, showI18nToast: vi.fn() };
});

// Spied pass-through: only the re-attach request of the attach case is answered by the test.
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, fetchWithTimeout: vi.fn(actual.fetchWithTimeout) };
});

const CHAT_ID = 'chat-turn-ownership';
const OTHER_CHAT_ID = 'chat-other';
const PANE_ID = 'pane-1';
const OTHER_PANE_ID = 'pane-2';
const MESSAGE_END = 'data: {"type":"message_end","messageId":"a-1"}\n\n';

/** The abort controller of every agent-stream request the pipeline made, in order. */
const requests: AbortController[] = [];

const store = () => useChatStore.getState();
/** Sends through the direct (non-multiplexed) transport, which the request assembly reads from this flag. */
const send = (input: string) => {
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  return store().sendMessage(input);
};
/**
 * Called by every request mock once the transport is chosen. A flag that stays set would send a finished turn
 * into the E2E-only loop that polls for pending approvals.
 */
const requestStarted = (request?: AbortController) => {
  delete window.__MYRM_E2E_DIRECT_SSE__;
  requests.push(request as AbortController);
};
// The first request waits for the cold request pipeline to load.
const eventually = (assertion: () => void) => vi.waitFor(assertion, { timeout: 15_000 });
/** Lets every held and every later reconcile call through. */
const releaseReconcile = () => {
  reconcile.hold = false;
  reconcile.waiting.splice(0).forEach((release) => release());
};
const paneHandle = () => useWorkspaceStore.getState().getPaneAbortController(PANE_ID);
const cancelRequests = () =>
  vi.mocked(cancelActiveChatAgent).mock.calls.length + vi.mocked(cancelAgentRequest).mock.calls.length;

const makeFile = (id: string): ChatFile => ({
  id,
  fileName: `${id}.txt`,
  fileExtension: 'txt',
  fileType: 'uploaded',
  fileUrl: `https://files.test/${id}`,
});

const makePane = (id: string, chatId: string): PaneConfig => ({
  id,
  chatId,
  title: id,
  snapshot: null,
  abortController: null,
  currentSessionMessageId: null,
});

/** An SSE reply the test ends by hand with a terminal event. */
function endingStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  return {
    response: new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }),
    end: () => {
      controller.enqueue(new TextEncoder().encode(MESSAGE_END));
      controller.close();
    },
  };
}

/** An SSE reply that keeps streaming until its request is aborted. */
function runningStream(request: AbortController): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        request.signal.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')));
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
}

/** Answers the first request with `first`, every later one with a stream that runs until stopped. */
function answerRequests(first: () => Promise<Response>) {
  vi.mocked(createAISearchStream)
    .mockImplementationOnce(async (_body: unknown, request?: AbortController) => {
      requestStarted(request);
      return first();
    })
    .mockImplementation(async (_body: unknown, request?: AbortController) => {
      requestStarted(request);
      return runningStream(request as AbortController);
    });
}

function resetWorld(withPane: boolean) {
  useToolApprovalStore.getState().clearAll();
  vi.mocked(cancelActiveChatAgent).mockClear();
  vi.mocked(cancelAgentRequest).mockClear();
  vi.mocked(createAISearchStream).mockReset();
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
  useWorkspaceStore.setState({
    panes: withPane ? [makePane(PANE_ID, CHAT_ID), makePane(OTHER_PANE_ID, OTHER_CHAT_ID)] : [],
    activePaneId: withPane ? PANE_ID : null,
  });
  useChatStore.setState({
    chatId: CHAT_ID,
    actionMode: 'agent',
    searchDepth: 'normal',
    agentConfig: null,
    abortController: null,
    loading: false,
    messages: [],
    files: [],
    cameraFrames: [],
    mentionReferences: [],
    currentSessionMessageId: null,
    currentBuiltinTools: ['web_search', 'memory'],
    incognitoMode: false,
    hideAttachList: false,
    messageAppeared: false,
    scheduleAutoSave: vi.fn(),
  });
}

describe('turn ownership of the shared turn state', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.spyOn(console, 'log').mockImplementation(() => undefined);
  });

  afterEach(() => {
    requests.splice(0).forEach((request) => request.abort());
    releaseReconcile();
    vi.useRealTimers();
    delete window.__MYRM_E2E_DIRECT_SSE__;
    vi.restoreAllMocks();
  });

  describe.each([{ withPane: false }, { withPane: true }])('chat pane: $withPane', ({ withPane }) => {
    it('keeps the next turn running and stoppable when the ended turn is still reconciling', async () => {
      resetWorld(withPane);
      reconcile.hold = true;
      const first = endingStream();
      answerRequests(async () => first.response);

      const firstTurn = send('first question');
      await eventually(() => expect(requests).toHaveLength(1));
      first.end();
      // The stream is over and the chat is idle again, while turn 1 still waits for the reconcile.
      await eventually(() => expect(store().loading).toBe(false));
      await eventually(() => expect(reconcile.waiting.length).toBeGreaterThan(0));

      const secondTurn = send('second question');
      await eventually(() => expect(requests).toHaveLength(2));
      // The composer already holds an attachment for the message after this one, and hides its attach list while
      // the message it sent is running.
      useChatStore.setState({ files: [makeFile('next')], hideAttachList: true });

      releaseReconcile();
      await firstTurn;

      expect(store().loading).toBe(true);
      expect(store().abortController).toBe(requests[1]);
      expect(store().currentSessionMessageId).not.toBeNull();
      expect(store().files.map((file) => file.id)).toEqual(['next']);
      expect(store().hideAttachList).toBe(true);
      if (withPane) {
        expect(paneHandle()).toBe(requests[1]);
      }

      store().stopMessage();
      await eventually(() => expect(requests[1].signal.aborted).toBe(true));
      expect(cancelRequests()).toBeGreaterThan(0);
      await secondTurn;
    });
  });

  it('ends a stopped turn that waits to retry without reporting a send failure', async () => {
    resetWorld(false);
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    vi.mocked(showI18nToast).mockClear();
    answerRequests(async () => {
      throw new TypeError('Failed to fetch');
    });

    const turn = send('only question');
    await eventually(() => expect(requests).toHaveLength(1));
    store().stopMessage();
    let turnEnded = false;
    void turn.then(() => {
      turnEnded = true;
    });

    await vi.advanceTimersByTimeAsync(100);
    expect(turnEnded).toBe(true);
    // The wait would have run out by now and failed the request the user already stopped.
    await vi.advanceTimersByTimeAsync(3_000);
    expect(vi.mocked(showI18nToast).mock.calls.map(([key]) => key)).not.toContain('chat.messageFailed.title');
    expect(store().messages.some((message) => message.sendFailed)).toBe(false);
    expect(requests).toHaveLength(1);
  });

  it('keeps a re-attached turn from ending the next turn when its reconcile outlives that turn', async () => {
    resetWorld(false);
    reconcile.hold = true;
    const attached = endingStream();
    vi.mocked(fetchWithTimeout).mockResolvedValueOnce(attached.response);
    vi.mocked(createAISearchStream).mockImplementation(async (_body: unknown, request?: AbortController) => {
      requestStarted(request);
      return runningStream(request as AbortController);
    });

    const attachTurn = attachToChat(CHAT_ID, store() as unknown as ChatActionsMethods, useChatStore.getState);
    await eventually(() => expect(store().loading).toBe(true));
    attached.end();
    await eventually(() => expect(store().loading).toBe(false));
    await eventually(() => expect(reconcile.waiting.length).toBeGreaterThan(0));

    const nextTurn = send('follow-up');
    await eventually(() => expect(requests).toHaveLength(1));

    releaseReconcile();
    await attachTurn;

    expect(store().loading).toBe(true);
    expect(store().abortController).toBe(requests[0]);

    store().stopMessage();
    await eventually(() => expect(requests[0].signal.aborted).toBe(true));
    expect(cancelRequests()).toBeGreaterThan(0);
    await nextTurn;
  });

  it('releases everything the turn owns when it is still the current one', async () => {
    resetWorld(false);
    // The composer hides its attach list while the message it sent is running.
    useChatStore.setState({ files: [makeFile('sent')], hideAttachList: true });
    const only = endingStream();
    answerRequests(async () => only.response);

    const turn = send('only question');
    await eventually(() => expect(store().abortController).toBe(requests[0]));
    expect(store().loading).toBe(true);
    only.end();
    await turn;
    // The terminal event also settles the stream from a 50 ms timer; wait for it so it cannot fire in a later test.
    await eventually(() => expect(store().messageAppeared).toBe(true));

    expect(store()).toMatchObject({
      loading: false,
      abortController: null,
      currentSessionMessageId: null,
      files: [],
      hideAttachList: false,
    });
  });

  it('releases the pane snapshot of a failed turn whose chat is no longer the active pane', async () => {
    resetWorld(true);
    let failRequest: () => void = () => undefined;
    vi.mocked(createAISearchStream).mockImplementationOnce(
      (_body: unknown, request?: AbortController) =>
        new Promise((_resolve, reject) => {
          requestStarted(request);
          failRequest = () => reject(new Error('provider rejected the request'));
        }),
    );

    const turn = send('background question');
    await eventually(() => expect(paneHandle()).toBeTruthy());
    // The user moves to the other pane while the request is pending; the pane snapshot is then a JSON clone.
    useWorkspaceStore.setState({ activePaneId: OTHER_PANE_ID });
    failRequest();
    await turn;

    const pane = useWorkspaceStore.getState().panes.find((entry) => entry.id === PANE_ID);
    expect(pane?.snapshot).toMatchObject({ loading: false, abortController: null, currentSessionMessageId: null });
    expect(pane?.abortController).toBeNull();
  });
});
