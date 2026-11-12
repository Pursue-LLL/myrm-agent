/**
 * Test kit for the stream consumer: stubs every collaborator that `consumeStream` and `executeStreamWithRetry` reach
 * (SSE schema, reducer, request pipeline, stores, e2ee, wiki metrics) and builds the responses and chat state the
 * tests feed them. A test file imports this kit before the modules under test: the stubs are registered while the kit
 * loads, and a module that loaded earlier keeps the real collaborators it imported.
 */
import { afterEach, beforeEach, vi } from 'vitest';
import type { ChatActionsMethods, ChatActionsState } from '../messageRequest';

const mockParseSseEnvelope = vi.hoisted(() => vi.fn());
const mockHandleMessageStream = vi.hoisted(() => vi.fn());
const mockCreateMessageRequest = vi.hoisted(() => vi.fn());
const mockAttachToChat = vi.hoisted(() => vi.fn());
const mockAttachForHitlRecovery = vi.hoisted(() => vi.fn());
const mockRecoverPendingApprovals = vi.hoisted(() => vi.fn());
const mockLoadMessages = vi.hoisted(() => vi.fn());
const mockReleaseTurnInspectorControls = vi.hoisted(() => vi.fn());
const mockResolveE2eApiBase = vi.hoisted(() => vi.fn<(...args: unknown[]) => string | null>(() => null));
const mockResolveChatWikiEvidenceContext = vi.hoisted(() => vi.fn());
const mockRecordWikiQuerySubmitted = vi.hoisted(() => vi.fn());
const mockConsumePendingChatWikiQuerySuccess = vi.hoisted(() => vi.fn());
const mockDecryptSseFrame = vi.hoisted(() => vi.fn());
const mockLoadStoredE2EESession = vi.hoisted(() => vi.fn<(...args: unknown[]) => unknown>(() => null));
const mockClearPendingWorkflowTemplate = vi.hoisted(() => vi.fn());
const approvalState = vi.hoisted(() => ({
  queue: [] as unknown[],
}));

export {
  mockParseSseEnvelope,
  mockHandleMessageStream,
  mockCreateMessageRequest,
  mockAttachToChat,
  mockAttachForHitlRecovery,
  mockRecoverPendingApprovals,
  mockLoadMessages,
  mockReleaseTurnInspectorControls,
  mockResolveE2eApiBase,
  mockResolveChatWikiEvidenceContext,
  mockRecordWikiQuerySubmitted,
  mockConsumePendingChatWikiQuerySuccess,
  mockDecryptSseFrame,
  mockLoadStoredE2EESession,
  mockClearPendingWorkflowTemplate,
  approvalState,
};

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

vi.mock('@/lib/inspector/releaseTurnInspectorControls', () => ({
  releaseTurnInspectorControls: (...args: unknown[]) => mockReleaseTurnInspectorControls(...args),
}));

vi.mock('@/hooks/approval/usePendingApprovalsRecovery', () => ({
  recoverPendingApprovals: (...args: unknown[]) => mockRecoverPendingApprovals(...args),
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

export function createBaseState(overrides: Partial<ChatActionsState> = {}): ChatActionsState {
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

export function createActions(state: ChatActionsState): ChatActionsMethods {
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

export function createSseResponse(raw: string): Response {
  return new Response(raw, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

export function createInterruptedResponse(rawChunk: string): Response {
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

export const STOP_TEST_EVENT = 'data: {"type":"message","messageId":"m-stop","data":"hi"}\n\n';

/** One event, then silence: the stream neither closes nor errors by itself once its turn is stopped. */
export function createSilentResponse(onCancel: () => void = () => undefined): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(textEncoder.encode(STOP_TEST_EVENT));
    },
    cancel: onCancel,
  });
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

export const HEARTBEAT_FRAME = 'event: heartbeat\ndata: null\n\n';

/** One event, then only what the test pushes: a stream that stays open while the model works without output. */
export function createPushedResponse(): { response: Response; push: (raw: string) => void } {
  const pusher = { push: (_raw: string): void => undefined };
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(textEncoder.encode(STOP_TEST_EVENT));
      pusher.push = (raw) => controller.enqueue(textEncoder.encode(raw));
    },
  });
  return {
    response: new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    push: (raw) => pusher.push(raw),
  };
}

/** One event, then a read failure the moment the turn is stopped: how an aborted fetch body behaves. */
export function createAbortFailingResponse(signal: AbortSignal): Response {
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
export function observe(promise: Promise<unknown>): { isSettled: () => boolean; error: () => unknown } {
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
export function eventually(assertion: () => void): Promise<void> {
  return vi.waitFor(assertion, { timeout: 5_000 });
}

/** Lets the reducer take the one event of `STOP_TEST_EVENT` and report it handled. */
export function armStreamHandlers(): void {
  mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'm-stop', data: 'hi' });
  mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'hi' });
}

function resetStreamConsumerMocks(): void {
  mockParseSseEnvelope.mockReset();
  mockHandleMessageStream.mockReset();
  mockCreateMessageRequest.mockReset();
  mockAttachToChat.mockReset();
  mockAttachForHitlRecovery.mockReset();
  mockRecoverPendingApprovals.mockReset();
  mockLoadMessages.mockReset();
  mockReleaseTurnInspectorControls.mockReset();
  mockResolveE2eApiBase.mockReset();
  mockResolveChatWikiEvidenceContext.mockReset();
  mockRecordWikiQuerySubmitted.mockReset();
  mockConsumePendingChatWikiQuerySuccess.mockReset();
  mockDecryptSseFrame.mockReset();
  mockLoadStoredE2EESession.mockReset();
  mockClearPendingWorkflowTemplate.mockReset();
  mockResolveE2eApiBase.mockReturnValue(null);
  mockResolveChatWikiEvidenceContext.mockReturnValue({ contextKey: 'chat:a-1', turnDistance: 0 });
  mockConsumePendingChatWikiQuerySuccess.mockReturnValue(undefined);
  mockLoadStoredE2EESession.mockReturnValue(null);
  approvalState.queue = [];
  mockAttachForHitlRecovery.mockResolvedValue({
    ok: true,
    attached: false,
    queueLen: 0,
    source: 'none',
  });
}

/** Puts every stub back to its default before each test and restores real timers after it. */
export function installStreamConsumerLifecycle(): void {
  beforeEach(resetStreamConsumerMocks);
  afterEach(() => {
    vi.useRealTimers();
  });
}
