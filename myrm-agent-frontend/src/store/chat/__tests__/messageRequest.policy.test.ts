/**
 * What the user's standing policies put on a turn's request: the security preset, the memory opt-in, the privacy
 * routing with its local model key, and a forced external agent.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createAISearchStream } from '@/services/chat';
import { getConfigSyncManager } from '@/services/config';
import type { AgentConfig } from '@/store/chat/types';
import { createMessageRequest, type ChatActionsState } from '@/store/chat/messageRequest';
import useConfigStore from '@/store/useConfigStore';
import useChatStore from '@/store/useChatStore';

vi.mock('@/services/chat', () => ({
  createAISearchStream: vi.fn(async () => new Response('', { status: 200 })),
}));

describe('messageRequest - security preset contract', () => {
  const makeState = (overrides: Record<string, unknown> = {}) =>
    ({
      chatId: 'chat-security',
      actionMode: 'agent',
      agentConfig: null,
      abortController: new AbortController(),
      loading: false,
      loadingOlder: false,
      messages: [],
      compactedSummary: null,
      compactedBeforeId: null,
      workspaceDir: null,
      files: [],
      visionFrames: [],
      hideAttachList: false,
      hasUsedImagesInCurrentChat: false,
      mentionReferences: [],
      clearMentionReferences: vi.fn(),
      removeMentionReferencesByTypes: vi.fn(),
      isGoalMode: false,
      goalBudgetTokens: null,
      goalBudgetUsd: null,
      goalMaxTimeSeconds: null,
      goalMaxTurns: null,
      goalProtectedPaths: null,
      goalLoopOnPause: false,
      goalConvergenceWindow: null,
      goalAcceptanceCriteria: null,
      goalConstraints: null,
      currentSessionMessageId: null,
      messageAppeared: false,
      isMessagesLoaded: true,
      hasMoreMessages: false,
      nextCursor: null,
      notFound: false,
      loadError: false,
      newChatCreated: false,
      currentBuiltinTools: [],
      ...overrides,
    }) as unknown as ChatActionsState;

  it.each(['hitl', 'accept_edits', 'explore'] as const)('always sends security_preset even for %s', async (preset) => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));
    useChatStore.setState({ securityPreset: preset });

    await createMessageRequest('security request', 'msg-sec', makeState(), null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).toMatchObject({ security_preset: preset });
  });
});

describe('messageRequest - memory settings contract', () => {
  it('includes enable_conversation_search when memory opt-in is enabled', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const originalMemoryEnableConversationSearch = useConfigStore.getState().memoryEnableConversationSearch;
    useConfigStore.setState({ memoryEnableConversationSearch: true });
    expect(useConfigStore.getState().memoryEnableConversationSearch).toBe(true);

    const state = {
      chatId: 'chat-memory-opt-in',
      actionMode: 'agent',
      agentConfig: null,
      abortController: new AbortController(),
      loading: false,
      loadingOlder: false,
      messages: [],
      compactedSummary: null,
      compactedBeforeId: null,
      workspaceDir: null,
      files: [],
      visionFrames: [],
      hideAttachList: false,
      hasUsedImagesInCurrentChat: false,
      mentionReferences: [],
      clearMentionReferences: vi.fn(),
      removeMentionReferencesByTypes: vi.fn(),
      isGoalMode: false,
      goalBudgetTokens: null,
      goalBudgetUsd: null,
      goalMaxTimeSeconds: null,
      goalMaxTurns: null,
      goalProtectedPaths: null,
      goalLoopOnPause: false,
      goalConvergenceWindow: null,
      goalAcceptanceCriteria: null,
      goalConstraints: null,
      currentSessionMessageId: null,
      messageAppeared: false,
      isMessagesLoaded: true,
      hasMoreMessages: false,
      nextCursor: null,
      notFound: false,
      loadError: false,
      newChatCreated: false,
      currentBuiltinTools: [],
      incognitoMode: false,
      searchDepth: 'normal' as const,
    } as unknown as ChatActionsState;

    await createMessageRequest('search prior chats', 'msg-memory-opt-in', state, null);

    expect(createAISearchStreamMock).toHaveBeenCalledTimes(1);
    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody.enable_conversation_search).toBe(true);

    useConfigStore.setState({ memoryEnableConversationSearch: originalMemoryEnableConversationSearch });
  });
});

describe('messageRequest - privacy routing contract', () => {
  const makeState = () =>
    ({
      chatId: 'chat-privacy-routing',
      actionMode: 'agent',
      agentConfig: null,
      abortController: new AbortController(),
      loading: false,
      loadingOlder: false,
      messages: [],
      compactedSummary: null,
      compactedBeforeId: null,
      workspaceDir: null,
      files: [],
      visionFrames: [],
      hideAttachList: false,
      hasUsedImagesInCurrentChat: false,
      mentionReferences: [],
      clearMentionReferences: vi.fn(),
      removeMentionReferencesByTypes: vi.fn(),
      isGoalMode: false,
      goalBudgetTokens: null,
      goalBudgetUsd: null,
      goalMaxTimeSeconds: null,
      goalMaxTurns: null,
      goalProtectedPaths: null,
      goalLoopOnPause: false,
      goalConvergenceWindow: null,
      goalAcceptanceCriteria: null,
      goalConstraints: null,
      currentSessionMessageId: null,
      messageAppeared: false,
      isMessagesLoaded: true,
      hasMoreMessages: false,
      nextCursor: null,
      notFound: false,
      loadError: false,
      newChatCreated: false,
      currentBuiltinTools: [],
    }) as unknown as ChatActionsState;

  const manager = getConfigSyncManager();
  const originalGet = manager.get.bind(manager);
  const preferences = {
    privacyEnabled: true,
    privacyRouting: { localModel: 'llama3:8b', s3Strategy: 'local' as const },
  };
  let savedKey: string | null = null;

  const sentRequest = async (): Promise<Record<string, unknown>> => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));
    await createMessageRequest('private question', 'msg-privacy-routing', makeState(), null);
    return (createAISearchStreamMock.mock.calls[0] ?? [])[0] as Record<string, unknown>;
  };

  beforeEach(() => {
    savedKey = null;
    vi.spyOn(manager, 'ensureKeyLoaded').mockResolvedValue(true);
    vi.spyOn(manager, 'get').mockImplementation(((key: string) =>
      key === 'privacyRoutingSecret' && savedKey ? { localApiKey: savedKey } : originalGet(key as never)) as never);
    useConfigStore.setState(preferences);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useConfigStore.setState({ privacyEnabled: false, privacyRouting: {} });
  });

  it('sends the saved local model key together with the routing preferences', async () => {
    savedKey = 'sk-local-endpoint';

    const body = await sentRequest();

    expect(body.privacy_routing).toEqual({
      localModel: 'llama3:8b',
      s3Strategy: 'local',
      localApiKey: 'sk-local-endpoint',
    });
  });

  it('keeps the key out of the persisted routing preferences', async () => {
    savedKey = 'sk-local-endpoint';

    await sentRequest();

    expect(JSON.stringify(useConfigStore.getState().privacyRouting)).not.toContain('sk-local-endpoint');
  });

  it('sends the routing preferences alone when no key was saved', async () => {
    const body = await sentRequest();

    expect(body.privacy_routing).toEqual({ localModel: 'llama3:8b', s3Strategy: 'local' });
  });

  it('sends no routing without a local model, and never sends the key then', async () => {
    savedKey = 'sk-local-endpoint';
    useConfigStore.setState({ privacyRouting: { s3Strategy: 'block' } });

    const body = await sentRequest();

    expect(body).not.toHaveProperty('privacy_routing');
    expect(JSON.stringify(body)).not.toContain('sk-local-endpoint');
  });

  it('sends no routing and no key when privacy mode is off', async () => {
    savedKey = 'sk-local-endpoint';
    useConfigStore.setState({ privacyEnabled: false });

    const body = await sentRequest();

    expect(body).not.toHaveProperty('privacy_routing');
    expect(JSON.stringify(body)).not.toContain('sk-local-endpoint');
  });
});

describe('messageRequest - force external agent delegation', () => {
  it('serializes force_external_agent when agentConfig.forceExternalAgent is set', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      chatId: 'chat-force-ext',
      actionMode: 'agent',
      agentConfig: { forceExternalAgent: 'echo-cli' } as AgentConfig,
      abortController: new AbortController(),
      loading: false,
      loadingOlder: false,
      messages: [],
      compactedSummary: null,
      compactedBeforeId: null,
      workspaceDir: null,
      files: [],
      visionFrames: [],
      hideAttachList: false,
      hasUsedImagesInCurrentChat: false,
      mentionReferences: [],
      clearMentionReferences: vi.fn(),
      removeMentionReferencesByTypes: vi.fn(),
      isGoalMode: false,
      goalBudgetTokens: null,
      goalBudgetUsd: null,
      goalMaxTimeSeconds: null,
      goalMaxTurns: null,
      goalProtectedPaths: null,
      goalLoopOnPause: false,
      goalConvergenceWindow: null,
      goalAcceptanceCriteria: null,
      goalConstraints: null,
      currentSessionMessageId: null,
      messageAppeared: false,
      isMessagesLoaded: true,
      hasMoreMessages: false,
      nextCursor: null,
      notFound: false,
      loadError: false,
      newChatCreated: false,
      currentBuiltinTools: [],
      searchDepth: 'normal' as const,
    } as unknown as ChatActionsState;

    await createMessageRequest('delegate to external cli', 'msg-force-ext', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).toMatchObject({
      action_mode: 'agent',
      force_external_agent: 'echo-cli',
    });
  });

  it('omits force_external_agent when forceExternalAgent is unset', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      chatId: 'chat-no-force-ext',
      actionMode: 'agent',
      agentConfig: null,
      abortController: new AbortController(),
      loading: false,
      loadingOlder: false,
      messages: [],
      compactedSummary: null,
      compactedBeforeId: null,
      workspaceDir: null,
      files: [],
      visionFrames: [],
      hideAttachList: false,
      hasUsedImagesInCurrentChat: false,
      mentionReferences: [],
      clearMentionReferences: vi.fn(),
      removeMentionReferencesByTypes: vi.fn(),
      isGoalMode: false,
      goalBudgetTokens: null,
      goalBudgetUsd: null,
      goalMaxTimeSeconds: null,
      goalMaxTurns: null,
      goalProtectedPaths: null,
      goalLoopOnPause: false,
      goalConvergenceWindow: null,
      goalAcceptanceCriteria: null,
      goalConstraints: null,
      currentSessionMessageId: null,
      messageAppeared: false,
      isMessagesLoaded: true,
      hasMoreMessages: false,
      nextCursor: null,
      notFound: false,
      loadError: false,
      newChatCreated: false,
      currentBuiltinTools: [],
      searchDepth: 'normal' as const,
    } as unknown as ChatActionsState;

    await createMessageRequest('normal agent request', 'msg-no-force-ext', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).not.toHaveProperty('force_external_agent');
  });
});
