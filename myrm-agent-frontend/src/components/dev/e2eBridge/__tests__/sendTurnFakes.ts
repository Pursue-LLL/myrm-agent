/**
 * Doubles shared by the send-pipeline tests (`e2eSubmitPreparation.test.ts`, `e2eSubmitObservation.test.ts`): the
 * stores, the progress reads and the timeline watcher the pipeline talks to, and the helpers that drive one send on a
 * fake clock. Each test file wires the module shapes of `mocks` in with an async `vi.mock` factory.
 *
 * Nothing here may import a module those factories replace (stores, `hostEnv`, `turnProgress`, ...): the factories
 * load this file, so such an import would wait on itself.
 */
import { vi } from 'vitest';

import type { submitAndObserveTurn } from '@/components/dev/e2eBridge/submitAndObserveTurn';

export type Debug = Record<string, unknown>;
export type Result = { ok: boolean; err?: string; mode?: string; chatId?: string | null; debug?: Debug };
export type RunOptions = {
  baseline?: number;
  profile?: 'live' | 'read';
  preserve?: boolean;
  ephemeral?: Record<string, unknown>;
};

export const START = 1_700_000_000_000;
export const NEVER = () => new Promise<boolean>(() => undefined);

export const world = {
  chat: {
    files: [] as unknown[],
    pendingExplicitSkillActivation: null as unknown,
    actionMode: 'agent',
    chatId: 'chat-1' as string | null,
    agentConfig: null as Record<string, unknown> | null,
    isMessagesLoaded: true,
    loading: false,
    abortController: null as unknown,
    currentSessionMessageId: '' as string | null,
    setInputMessage: vi.fn(),
    clearCurrentSessionMessageId: vi.fn(),
    setActionMode: vi.fn(),
    sendMessage: vi.fn(),
  },
  approvals: {
    processingMessageIds: new Set<string>(),
    queue: [] as unknown[],
    unmarkProcessing: vi.fn(),
    clearAll: vi.fn(),
  },
  config: { searchServiceConfigs: [] as Array<{ enabled: boolean }> },
  generation: { value: 0 },
  progress: { value: { userCount: 0, streaming: false, uiProgress: false } },
  api: { users: 0 },
  guardSearchServiceConfigured: vi.fn(),
  getModelSelection: vi.fn(),
  prepareAutomationSend: vi.fn(),
  resolveE2eTurnProgress: vi.fn(),
  pollApiUserMessages: vi.fn(),
  watchChatStoreTimeline: vi.fn(),
};

/** The page-side bridge (`window.__MYRM_E2E_CHAT__`) the pipeline calls into. */
export const bridge = {
  abortActiveStream: vi.fn(),
  releaseActiveStreamForApiResume: vi.fn(),
  ensureChatSession: vi.fn(),
  isSendReady: vi.fn(),
  debugProviderState: vi.fn(),
  turnSnapshot: vi.fn(),
};

export const watch = { snapshot: vi.fn(), stop: vi.fn() };

/** Module shapes for the `vi.mock` factories. */
export const mocks = {
  chatStore: { default: { getState: () => world.chat } },
  approvalStore: { default: { getState: () => world.approvals } },
  configStore: { default: { getState: () => world.config } },
  searchService: { guardSearchServiceConfigured: world.guardSearchServiceConfigured },
  messageRequest: { getModelSelection: world.getModelSelection },
  turnProgress: {
    readE2eSendGeneration: () => world.generation.value,
    resolveE2eTurnProgress: world.resolveE2eTurnProgress,
    pollApiUserMessages: world.pollApiUserMessages,
  },
  storeTimelineWatcher: { watchChatStoreTimeline: world.watchChatStoreTimeline },
};

export function resetWorld(): void {
  vi.useFakeTimers();
  vi.setSystemTime(START);
  Object.assign(world.chat, {
    files: [],
    pendingExplicitSkillActivation: null,
    actionMode: 'agent',
    chatId: 'chat-1',
    agentConfig: null,
    isMessagesLoaded: true,
    loading: false,
    abortController: null,
    currentSessionMessageId: '',
  });
  world.chat.setInputMessage.mockReset();
  world.chat.clearCurrentSessionMessageId.mockReset();
  world.chat.setActionMode.mockReset().mockImplementation((mode: string) => {
    world.chat.actionMode = mode;
  });
  world.chat.sendMessage.mockReset().mockImplementation(NEVER);
  world.approvals.processingMessageIds = new Set(['req-9']);
  world.approvals.queue = [];
  world.approvals.unmarkProcessing.mockReset();
  world.approvals.clearAll.mockReset();
  world.config.searchServiceConfigs = [];
  world.generation.value = 4;
  world.progress.value = { userCount: 0, streaming: false, uiProgress: false };
  world.api.users = 0;
  world.guardSearchServiceConfigured.mockReset().mockReturnValue(true);
  world.getModelSelection.mockReset().mockReturnValue({ providerId: 'p', model: 'm' });
  world.prepareAutomationSend.mockReset();
  world.resolveE2eTurnProgress.mockReset().mockImplementation(() => world.progress.value);
  world.pollApiUserMessages
    .mockReset()
    .mockImplementation(async () => ({ users: world.api.users, notFound: false, failure: null }));
  watch.snapshot.mockReset().mockReturnValue({ marker: 'store-timeline' });
  watch.stop.mockReset();
  world.watchChatStoreTimeline.mockReset().mockReturnValue(watch);
  bridge.abortActiveStream.mockReset();
  bridge.releaseActiveStreamForApiResume.mockReset();
  bridge.ensureChatSession.mockReset().mockResolvedValue(undefined);
  bridge.isSendReady.mockReset().mockReturnValue(true);
  bridge.debugProviderState.mockReset().mockReturnValue({ providerIds: ['p1'] });
  bridge.turnSnapshot.mockReset().mockReturnValue({ userCount: 2 });
  window.__MYRM_E2E_CHAT__ = bridge as unknown as Window['__MYRM_E2E_CHAT__'];
}

export function restoreWorld(): void {
  vi.useRealTimers();
  delete window.__MYRM_E2E_CHAT__;
  delete window.__MYRM_E2E_EPH_APPLIED__;
}

/**
 * Runs one send to its result on the fake clock. `enoughMs` outlasts every wait of the pipeline; the promise ends
 * earlier, at the first exit it reaches.
 */
export function createRun(submit: typeof submitAndObserveTurn, enoughMs: number) {
  return async (message = 'hello', options: RunOptions = {}): Promise<Result> => {
    const pending = submit(
      message,
      options.baseline ?? 0,
      options.profile ?? 'live',
      options.preserve ?? false,
      options.ephemeral,
    );
    await vi.advanceTimersByTimeAsync(enoughMs);
    return pending;
  };
}

/** Progress in the UI and a user row in the API: the two signals a send needs to seal. */
export function sealable(): void {
  world.progress.value = { userCount: 1, streaming: true, uiProgress: true };
  world.api.users = 1;
}

export const debugOf = (result: Result): Debug => result.debug ?? {};
const sorted = (keys: string[]): string[] => [...keys].sort();
export const keysOf = (result: Result): string[] => sorted(Object.keys(debugOf(result)));

export const DIAGNOSTIC_KEYS = ['approvalQueueLen', 'chatId', 'processingIds', 'provider', 'rev', 'turn', 'workspace'];
export const EVIDENCE_KEYS = ['storeTimeline', 'turnTrace'];
export const OBSERVED_KEYS = [
  'apiPoll',
  'apiUsers',
  'baselineUsers',
  'phase',
  'profile',
  'sendGeneration',
  'streaming',
  'userCount',
];
/** The debug keys of a result: the groups it is made of, sorted. */
export const keySet = (...groups: string[][]): string[] => sorted(groups.flat());
