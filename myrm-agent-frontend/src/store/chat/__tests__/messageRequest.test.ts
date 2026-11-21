/**
 * The envelope of a turn's request: the reply locale, the effective agent id, a typed archive restore, the
 * one-turn capability telemetry and the transport the turn is answered on.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { createAISearchStream } from '@/services/chat';
import { DEFAULT_PERSONAL_SETTINGS } from '@/services/config/types';
import type { AgentConfig } from '@/store/chat/types';
import { createMessageRequest, resolveEffectiveAgentId, type ChatActionsState } from '@/store/chat/messageRequest';
import useConfigStore from '@/store/useConfigStore';

vi.mock('@/services/chat', () => ({
  createAISearchStream: vi.fn(async () => new Response('', { status: 200 })),
}));

describe('messageRequest - reply locale contract', () => {
  const makeState = () =>
    ({
      chatId: 'chat-locale',
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

  const originalPersonalSettings = useConfigStore.getState().personalSettings;

  afterEach(() => {
    useConfigStore.setState({ personalSettings: originalPersonalSettings });
    document.cookie = 'NEXT_LOCALE=; path=/; max-age=0';
  });

  async function requestedLocale(saved: string | undefined, cookie: string | null): Promise<unknown> {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));
    useConfigStore.setState({ personalSettings: { ...DEFAULT_PERSONAL_SETTINGS, locale: saved } });
    if (cookie) {
      document.cookie = `NEXT_LOCALE=${cookie}; path=/`;
    }

    await createMessageRequest('which language', 'msg-locale', makeState(), null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    return requestBody.locale;
  }

  it('answers in the saved locale, in the backend format', async () => {
    expect(await requestedLocale('zh-CN', 'en')).toBe('zh-CN');
    expect(await requestedLocale('en', 'zh')).toBe('en');
  });

  it('follows the interface language when nothing is saved', async () => {
    expect(await requestedLocale(undefined, 'zh')).toBe('zh-CN');
    expect(await requestedLocale(undefined, 'en')).toBe('en');
  });

  it.each(['ja', 'ko', 'de'])(
    'follows the interface language when the saved locale is the unsupported %s',
    async (unsupported) => {
      expect(await requestedLocale(unsupported, 'zh')).toBe('zh-CN');
      expect(await requestedLocale(unsupported, 'en')).toBe('en');
    },
  );

  it('sends no locale when neither source names an offered one', async () => {
    expect(await requestedLocale('ja', null)).toBeUndefined();
  });
});

describe('messageRequest - agent id fallback', () => {
  const baseAgentConfig: AgentConfig = {
    selectedSkillIds: [],
    selectedMcpNames: [],
    systemPrompt: '',
    useGlobalInstruction: true,
  };

  it('should default to builtin-general in agent mode when no agent is selected', () => {
    expect(resolveEffectiveAgentId('agent', null)).toBe('builtin-general');
  });

  it('should preserve an explicit agent id in agent mode', () => {
    expect(
      resolveEffectiveAgentId('agent', {
        ...baseAgentConfig,
        agentId: 'builtin-writer',
      }),
    ).toBe('builtin-writer');
  });

  it('should return builtin-fast-search in fast mode with normal depth', () => {
    expect(resolveEffectiveAgentId('fast', baseAgentConfig, 'normal')).toBe('builtin-fast-search');
  });

  it('should return builtin-fast-search in fast mode with deep depth', () => {
    expect(resolveEffectiveAgentId('fast', baseAgentConfig, 'deep')).toBe('builtin-fast-search');
  });

  it('should return builtin-fast-search in fast mode when depth is undefined', () => {
    expect(resolveEffectiveAgentId('fast', baseAgentConfig)).toBe('builtin-fast-search');
  });

  it('should remap hidden builtin-researcher to builtin-general in agent mode', () => {
    expect(
      resolveEffectiveAgentId('agent', {
        ...baseAgentConfig,
        agentId: 'builtin-researcher',
      }),
    ).toBe('builtin-general');
  });
});

describe('messageRequest - archive restore contract', () => {
  it('serializes typed archive restore actions into the backend request contract', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));
    const abortController = new AbortController();
    const state = {
      chatId: 'chat-1',
      actionMode: 'agent',
      agentConfig: null,
      abortController,
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
    } as unknown as ChatActionsState;

    await createMessageRequest('restore archived evidence', 'msg-1', state, null, undefined, [
      {
        type: 'archive_restore',
        restoreArg: '.context/chat-1/compacted/result.txt:20-40',
      },
    ]);

    const [requestBody, signal] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(signal).toBe(abortController);
    expect(requestBody).toMatchObject({
      query: 'restore archived evidence',
      message_id: 'msg-1',
      chat_id: 'chat-1',
      archive_restore_actions: [
        {
          type: 'archive_restore',
          restore_arg: '.context/chat-1/compacted/result.txt:20-40',
        },
      ],
    });
    expect(requestBody).not.toHaveProperty('archiveRestoreActions');
  });
});

describe('messageRequest - turn capability telemetry contract', () => {
  it('serializes one-turn capability terminal telemetry in snake_case', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      chatId: 'chat-telemetry',
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
    } as unknown as ChatActionsState;

    await createMessageRequest('telemetry request', 'msg-telemetry', state, null, undefined, undefined, {
      source: 'direct',
      effectiveSkillCount: 2,
      effectiveMcpCount: 1,
    });

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).toMatchObject({
      turn_capability_telemetry: {
        source: 'direct',
        effective_skill_count: 2,
        effective_mcp_count: 1,
      },
    });
    expect(requestBody).not.toHaveProperty('turnCapabilityTelemetry');
  });
});

describe('messageRequest - turn transport contract', () => {
  it('answers a turn on the POST response body: the request carries no transport switch', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));
    const state = {
      chatId: 'chat-transport',
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
      currentSessionMessageId: null,
      messageAppeared: false,
      isMessagesLoaded: true,
      hasMoreMessages: false,
      nextCursor: null,
      notFound: false,
      loadError: false,
      newChatCreated: false,
      currentBuiltinTools: [],
    } as unknown as ChatActionsState;

    await createMessageRequest('plain turn', 'msg-transport', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).toMatchObject({ message_id: 'msg-transport', action_mode: 'agent' });
    expect(requestBody).not.toHaveProperty('multiplexed');
  });
});
