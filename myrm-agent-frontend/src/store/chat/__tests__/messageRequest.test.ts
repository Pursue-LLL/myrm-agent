import { describe, it, expect, vi, beforeEach } from 'vitest';
import { setGlobalTranslator } from '@/services/i18nToastService';
import * as api from '@/lib/api';
import { createAISearchStream } from '@/services/chat';
import { normalizeLocaleForBackend } from '@/lib/utils/localeUtils';
import type { AgentConfig } from '@/store/chat/types';
import type { MentionReference } from '@/store/chat/types';
import {
  createMessageRequest,
  resolveEffectiveAgentId,
  sendMessage,
  type ChatActionsMethods,
  type ChatActionsState,
} from '@/store/chat/messageRequest';
import useConfigStore from '@/store/useConfigStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import useChatStore from '@/store/useChatStore';

const showI18nToastMock = vi.hoisted(() => vi.fn());
const resolveKanbanSendBlockReasonMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/i18nToastService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/i18nToastService')>();
  return {
    ...actual,
    showI18nToast: (...args: unknown[]) => showI18nToastMock(...args),
  };
});

vi.mock('@/services/chat', () => ({
  createAISearchStream: vi.fn(async () => new Response('', { status: 200 })),
}));

vi.mock('@/lib/kanban/kanbanChatBoard', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/kanban/kanbanChatBoard')>();
  return {
    ...actual,
    resolveKanbanSendBlockReason: (...args: unknown[]) => resolveKanbanSendBlockReasonMock(...args),
  };
});

/**
 * Test locale priority logic from messageRequest.ts
 * Logic: prioritize personalSettings.locale > cookie > auto-detect
 */
describe('messageRequest - locale priority logic', () => {
  it('should prioritize personalSettings.locale over cookie', () => {
    // Simulate personalSettings with locale
    const mockConfigStore = {
      personalSettings: {
        locale: 'zh-CN',
      },
    };

    const mockCookieLocale = 'en'; // cookie is 'en'

    // Simulate the logic from messageRequest.ts
    const savedLocale = mockConfigStore.personalSettings?.locale;
    const userLocale = normalizeLocaleForBackend(savedLocale || mockCookieLocale);

    expect(userLocale).toBe('zh-CN'); // personalSettings wins
    expect(savedLocale).toBe('zh-CN');
  });

  it('should fallback to cookie when personalSettings.locale is undefined', () => {
    // Simulate personalSettings without locale
    const mockConfigStore: { personalSettings: { locale?: string } } = {
      personalSettings: {
        // no locale field
      },
    };

    const mockCookieLocale = 'en';

    const savedLocale = mockConfigStore.personalSettings?.locale;
    const userLocale = normalizeLocaleForBackend(savedLocale || mockCookieLocale);

    expect(userLocale).toBe('en'); // fallback to cookie
    expect(savedLocale).toBeUndefined();
  });

  it('should fallback to cookie when personalSettings is null', () => {
    // Simulate null personalSettings
    const mockConfigStore = {
      personalSettings: null as { locale?: string } | null,
    };

    const mockCookieLocale = 'en';

    const savedLocale = mockConfigStore.personalSettings?.locale;
    const userLocale = normalizeLocaleForBackend(savedLocale || mockCookieLocale);

    expect(userLocale).toBe('en'); // fallback to cookie
    expect(savedLocale).toBeUndefined();
  });

  it('should normalize zh from personalSettings to zh-CN', () => {
    const mockConfigStore = {
      personalSettings: {
        locale: 'zh',
      },
    };

    const mockCookieLocale = 'en';

    const savedLocale = mockConfigStore.personalSettings?.locale;
    const userLocale = normalizeLocaleForBackend(savedLocale || mockCookieLocale);

    // normalizeLocaleForBackend normalizes 'zh' to 'zh-CN'
    expect(userLocale).toBe('zh-CN');
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

  it('should default to builtin-general in deep_research mode', () => {
    expect(resolveEffectiveAgentId('deep_research', baseAgentConfig)).toBe('builtin-general');
  });

  it('should remap hidden researcher agent to builtin-general in deep_research mode', () => {
    expect(
      resolveEffectiveAgentId('deep_research', {
        ...baseAgentConfig,
        agentId: 'builtin-researcher',
      }),
    ).toBe('builtin-general');
  });

  it('should return builtin-fast-search in fast mode when depth is undefined', () => {
    expect(resolveEffectiveAgentId('fast', baseAgentConfig)).toBe('builtin-fast-search');
  });

  it('should preserve explicit custom agent id in deep_research mode', () => {
    expect(
      resolveEffectiveAgentId('deep_research', {
        ...baseAgentConfig,
        agentId: 'custom-agent',
      }),
    ).toBe('custom-agent');
  });

  it('should remap hidden builtin-researcher to builtin-general in agent mode', () => {
    expect(
      resolveEffectiveAgentId('agent', {
        ...baseAgentConfig,
        agentId: 'builtin-researcher',
      }),
    ).toBe('builtin-general');
  });

  it('should return undefined for claude_code mode', () => {
    expect(resolveEffectiveAgentId('claude_code', baseAgentConfig)).toBeUndefined();
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
      cameraFrames: [],
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
      cameraFrames: [],
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

    await createMessageRequest(
      'telemetry request',
      'msg-telemetry',
      state,
      null,
      undefined,
      undefined,
      {
        source: 'direct',
        effectiveSkillCount: 2,
        effectiveMcpCount: 1,
      },
    );

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
      cameraFrames: [],
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

  it.each(['hitl', 'accept_edits', 'explore'] as const)(
    'always sends security_preset even for %s',
    async (preset) => {
      const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
      createAISearchStreamMock.mockClear();
      createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));
      useChatStore.setState({ securityPreset: preset });

      await createMessageRequest('security request', 'msg-sec', makeState(), null);

      const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
      expect(requestBody).toMatchObject({ security_preset: preset });
    },
  );
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
      cameraFrames: [],
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
      sandboxMode: false,
      searchDepth: 'normal' as const,
    } as unknown as ChatActionsState;

    await createMessageRequest('search prior chats', 'msg-memory-opt-in', state, null);

    expect(createAISearchStreamMock).toHaveBeenCalledTimes(1);
    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody.enable_conversation_search).toBe(true);

    useConfigStore.setState({ memoryEnableConversationSearch: originalMemoryEnableConversationSearch });
  });
});

describe('messageRequest - goal payload construction', () => {
  beforeEach(() => {
    (createAISearchStream as ReturnType<typeof vi.fn>).mockClear();
  });

  const baseGoalState = {
    chatId: 'chat-goal',
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
    cameraFrames: [],
    hideAttachList: false,
    hasUsedImagesInCurrentChat: false,
    mentionReferences: [],
    clearMentionReferences: vi.fn(),
    removeMentionReferencesByTypes: vi.fn(),
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
    sandboxMode: false,
    searchDepth: 'normal' as const,
  };

  it('sends all goal budget fields when isGoalMode is true', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      ...baseGoalState,
      isGoalMode: true,
      goalBudgetTokens: 50000,
      goalBudgetUsd: 5.0,
      goalMaxTimeSeconds: 3600,
      goalMaxTurns: 30,
      goalProtectedPaths: ['*.env', 'config/**'],
      goalLoopOnPause: true,
      goalConvergenceWindow: 3,
      goalAcceptanceCriteria: [{ type: 'shell', command: 'pytest' }],
      goalConstraints: ['No destructive ops'],
    } as unknown as ChatActionsState;

    try {
      await createMessageRequest('test goal', 'msg-goal-1', state, null);
    } catch {
      // createMessageRequest may throw if some stores are not fully mocked
    }

    expect(createAISearchStreamMock).toHaveBeenCalled();
    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody.goal).toBeDefined();
    expect(requestBody.goal.max_tokens).toBe(50000);
    expect(requestBody.goal.max_usd).toBe(5.0);
    expect(requestBody.goal.max_time_seconds).toBe(3600);
    expect(requestBody.goal.max_turns).toBe(30);
    expect(requestBody.goal.convergence_window).toBe(3);
    expect(requestBody.goal.loop_on_pause).toBe(true);
    expect(requestBody.goal.protected_paths).toEqual(['*.env', 'config/**']);
    expect(requestBody.goal.acceptance_criteria).toEqual([{ type: 'shell', command: 'pytest' }]);
    expect(requestBody.goal.constraints).toEqual(['No destructive ops']);
  });

  it('omits null budget fields from goal payload', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      ...baseGoalState,
      isGoalMode: true,
      goalBudgetTokens: null,
      goalBudgetUsd: null,
      goalMaxTimeSeconds: null,
      goalMaxTurns: null,
      goalProtectedPaths: null,
      goalLoopOnPause: false,
      goalConvergenceWindow: null,
      goalAcceptanceCriteria: null,
      goalConstraints: null,
    } as unknown as ChatActionsState;

    try {
      await createMessageRequest('minimal goal', 'msg-goal-2', state, null);
    } catch {
      // may throw if stores not fully mocked
    }

    expect(createAISearchStreamMock).toHaveBeenCalled();
    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody.goal).toBeDefined();
    expect(requestBody.goal).not.toHaveProperty('max_tokens');
    expect(requestBody.goal).not.toHaveProperty('max_usd');
    expect(requestBody.goal).not.toHaveProperty('max_time_seconds');
    expect(requestBody.goal).not.toHaveProperty('max_turns');
    expect(requestBody.goal).not.toHaveProperty('convergence_window');
    expect(requestBody.goal).not.toHaveProperty('loop_on_pause');
    expect(requestBody.goal).not.toHaveProperty('protected_paths');
    expect(requestBody.goal).not.toHaveProperty('acceptance_criteria');
    expect(requestBody.goal).not.toHaveProperty('constraints');
  });

  it('does not include goal object when isGoalMode is false', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      ...baseGoalState,
      isGoalMode: false,
      goalBudgetTokens: 50000,
      goalBudgetUsd: 5.0,
      goalMaxTimeSeconds: 3600,
      goalMaxTurns: 30,
      goalProtectedPaths: ['*.env'],
      goalLoopOnPause: true,
      goalConvergenceWindow: 3,
      goalAcceptanceCriteria: null,
      goalConstraints: null,
    } as unknown as ChatActionsState;

    try {
      await createMessageRequest('no goal mode', 'msg-goal-3', state, null);
    } catch {
      // may throw if stores not fully mocked
    }

    expect(createAISearchStreamMock).toHaveBeenCalled();
    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).not.toHaveProperty('goal');
  });

  it('filters empty strings from constraints and protected_paths', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      ...baseGoalState,
      isGoalMode: true,
      goalBudgetTokens: 10000,
      goalBudgetUsd: null,
      goalMaxTimeSeconds: null,
      goalMaxTurns: null,
      goalProtectedPaths: ['*.env', '', '  ', 'config/**'],
      goalLoopOnPause: false,
      goalConvergenceWindow: null,
      goalAcceptanceCriteria: null,
      goalConstraints: ['valid constraint', '', '   '],
    } as unknown as ChatActionsState;

    try {
      await createMessageRequest('filter test', 'msg-goal-4', state, null);
    } catch {
      // may throw if stores not fully mocked
    }

    expect(createAISearchStreamMock).toHaveBeenCalled();
    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody.goal.protected_paths).toEqual(['*.env', 'config/**']);
    expect(requestBody.goal.constraints).toEqual(['valid constraint']);
  });
});

describe('messageRequest - processing lock lifecycle', () => {
  it('releases the processing lock when search service validation fails', async () => {
    setGlobalTranslator((key) => key);
    useToolApprovalStore.getState().clearAll();
    const originalSearchServiceConfigs = useConfigStore.getState().searchServiceConfigs;
    useConfigStore.setState({ searchServiceConfigs: [] });
    const fetchWithTimeoutSpy = vi.spyOn(api, 'fetchWithTimeout').mockResolvedValue(new Response('', { status: 200 }));

    const originalMarkProcessing = useToolApprovalStore.getState().markProcessing;
    const originalUnmarkProcessing = useToolApprovalStore.getState().unmarkProcessing;

    const markProcessing = vi.fn((messageId: string) => originalMarkProcessing(messageId));
    const unmarkProcessing = vi.fn((messageId: string) => originalUnmarkProcessing(messageId));

    useToolApprovalStore.setState({
      markProcessing,
      unmarkProcessing,
    });

    const state = {
      chatId: 'chat-1',
      actionMode: 'agent',
      agentConfig: null,
      abortController: null,
      loading: false,
      loadingOlder: false,
      messages: [],
      compactedSummary: null,
      compactedBeforeId: null,
      workspaceDir: null,
      files: [],
      cameraFrames: [],
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
      currentBuiltinTools: ['web_search'],
    } as unknown as ChatActionsState;

    const actions = {
      setMessages: vi.fn(),
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
      setHideAttachList: vi.fn(),
      setHasUsedImagesInCurrentChat: vi.fn(),
      setSelectedModels: vi.fn(),
      setHasUserSelectedModel: vi.fn(),
      clearCurrentSessionMessageId: vi.fn(),
      _processSuggestions: vi.fn(),
      scheduleAutoSave: vi.fn(),
      setInputMessage: vi.fn(),
    } as unknown as ChatActionsMethods;

    await sendMessage('请测试处理锁释放', 'req-1', state, actions, () => 'req-1', () => 'req-1-alloc');

    expect(markProcessing).toHaveBeenCalledTimes(1);
    expect(markProcessing).toHaveBeenCalledWith('req-1');
    expect(unmarkProcessing).toHaveBeenCalledTimes(1);
    expect(unmarkProcessing).toHaveBeenCalledWith('req-1');
    expect(useToolApprovalStore.getState().isProcessing('req-1')).toBe(false);
    fetchWithTimeoutSpy.mockRestore();

    useToolApprovalStore.setState({
      markProcessing: originalMarkProcessing,
      unmarkProcessing: originalUnmarkProcessing,
    });
    useConfigStore.setState({ searchServiceConfigs: originalSearchServiceConfigs });
    useToolApprovalStore.getState().clearAll();
  });
});

describe('messageRequest - send preconditions', () => {
  const baseActions = {
    setMessages: vi.fn(),
    setLoading: vi.fn(),
    setMessageAppeared: vi.fn(),
    setHideAttachList: vi.fn(),
    setHasUsedImagesInCurrentChat: vi.fn(),
    setSelectedModels: vi.fn(),
    setHasUserSelectedModel: vi.fn(),
    clearCurrentSessionMessageId: vi.fn(),
    _processSuggestions: vi.fn(),
    scheduleAutoSave: vi.fn(),
    setInputMessage: vi.fn(),
  } as unknown as ChatActionsMethods;

  const baseState = {
    chatId: 'chat-1',
    actionMode: 'agent',
    searchDepth: 'normal',
    agentConfig: null,
    abortController: null,
    loading: false,
    loadingOlder: false,
    messages: [],
    compactedSummary: null,
    compactedBeforeId: null,
    workspaceDir: null,
    files: [],
    mentionReferences: [],
    cameraFrames: [],
    hideAttachList: false,
    hasUsedImagesInCurrentChat: false,
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
    incognitoMode: false,
    sandboxMode: false,
    notFound: false,
    loadError: false,
    newChatCreated: false,
    currentBuiltinTools: ['web_search', 'memory'],
    clearMentionReferences: vi.fn(),
    removeMentionReferencesByTypes: vi.fn(),
  } as unknown as ChatActionsState;

  beforeEach(() => {
    showI18nToastMock.mockClear();
    resolveKanbanSendBlockReasonMock.mockReset();
    resolveKanbanSendBlockReasonMock.mockResolvedValue(null);
    useToolApprovalStore.getState().clearAll();
  });

  it('shows toast when chat session is missing', async () => {
    await sendMessage(
      'hello',
      'req-no-chat',
      { ...baseState, chatId: undefined },
      baseActions,
      () => 'req-no-chat',
      () => 'req-no-chat-alloc',
    );

    expect(showI18nToastMock).toHaveBeenCalledWith(
      'chat.sendBlocked.title',
      undefined,
      expect.objectContaining({ descriptionKey: 'chat.sendBlocked.noChatDescription' }),
    );
  });

  it('shows toast when approval processing lock is active', async () => {
    useToolApprovalStore.getState().markProcessing('req-lock');

    await sendMessage('hello', 'req-lock', baseState, baseActions, () => 'req-lock', () => 'req-lock-alloc');

    expect(showI18nToastMock).toHaveBeenCalledWith(
      'chat.sendBlocked.title',
      undefined,
      expect.objectContaining({ descriptionKey: 'chat.sendBlocked.processingDescription' }),
    );
  });

  it('shows toast when kanban enabled but no target board selected', async () => {
    resolveKanbanSendBlockReasonMock.mockResolvedValue('need_board');

    await sendMessage(
      'hello',
      'req-kanban',
      { ...baseState, currentBuiltinTools: ['kanban'] },
      baseActions,
      () => 'req-kanban',
      () => 'req-kanban-alloc',
    );

    expect(resolveKanbanSendBlockReasonMock).toHaveBeenCalledWith(['kanban'], null);
    expect(showI18nToastMock).toHaveBeenCalledWith(
      'chat.sendBlocked.title',
      undefined,
      expect.objectContaining({ descriptionKey: 'chat.sendBlocked.kanbanNeedBoardDescription' }),
    );
  });
});

describe('messageRequest - active moa preset', () => {
  beforeEach(() => {
    useChatStore.setState({ activeMoaPresetId: null });
  });

  it('serializes active_moa_preset_id in agent mode when session preset is set', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    useChatStore.setState({ activeMoaPresetId: 'default' });

    const state = {
      chatId: 'chat-moa',
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
      cameraFrames: [],
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

    await createMessageRequest('moa request', 'msg-moa', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).toMatchObject({
      action_mode: 'agent',
      active_moa_preset_id: 'default',
    });
  });

  it('includes workflow_template_id while pending template is armed', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    useChatStore.setState({
      pendingWorkflowTemplateId: 'demo-flow',
      pendingWorkflowTemplateArgs: { topic: 'billing' },
      pendingWorkflowTemplateDisplayName: 'Demo Flow',
    });

    const state = {
      chatId: 'chat-template',
      abortController: new AbortController(),
      actionMode: 'agent',
      searchDepth: 'normal',
      agentConfig: null,
      currentBuiltinTools: [],
      isWorkflowMode: false,
      loading: false,
      messages: [],
      files: [],
      cameraFrames: [],
      hideAttachList: false,
      hasUsedImagesInCurrentChat: false,
      mentionReferences: [],
      clearMentionReferences: vi.fn(),
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
    } as unknown as ChatActionsState;

    await createMessageRequest('pinned rerun', 'msg-template', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls.at(-1) ?? [];
    expect(requestBody).toMatchObject({
      use_workflow: true,
      workflow_template_id: 'demo-flow',
      workflow_template_args: { topic: 'billing' },
    });
  });
});

describe('messageRequest - mention reference lifetime contract', () => {
  const baseState = {
    chatId: 'chat-ref',
    actionMode: 'agent',
    searchDepth: 'normal',
    agentConfig: null,
    abortController: new AbortController(),
    loading: false,
    loadingOlder: false,
    messages: [],
    compactedSummary: null,
    compactedBeforeId: null,
    workspaceDir: null,
    files: [],
    cameraFrames: [],
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

  it('drops a zombie agent mention once its @token is removed from the input', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      ...baseState,
      mentionReferences: [
        { type: 'agent', label: '@研究专家', fileId: 'agent-1', source: 'special', size: null, viaText: true },
      ] satisfies MentionReference[],
    };
    await createMessageRequest('帮我分析竞品文档', 'msg-zombie-agent', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).not.toHaveProperty('mentioned_agent_ids');
  });

  it('keeps an agent mention while its @token still exists in the input', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      ...baseState,
      mentionReferences: [
        { type: 'agent', label: '@研究专家', fileId: 'agent-1', source: 'special', size: null, viaText: true },
      ] satisfies MentionReference[],
    };
    await createMessageRequest('@研究专家 帮我分析竞品文档', 'msg-live-agent', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).toMatchObject({ mentioned_agent_ids: ['agent-1'] });
  });

  it('drops a zombie wiki mention once its @wiki token is removed from the input', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      ...baseState,
      mentionReferences: [
        {
          type: 'wiki_concept',
          label: '@wiki:机器学习',
          conceptName: '机器学习',
          source: 'wiki',
          size: null,
          viaText: true,
        },
      ] satisfies MentionReference[],
    };
    await createMessageRequest('总结一下这篇文档', 'msg-zombie-wiki', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).not.toHaveProperty('mention_references');
  });

  it('drops a zombie prior_chat mention once its @chat token is removed from the input', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      ...baseState,
      mentionReferences: [
        {
          type: 'prior_chat',
          label: '@chat:Alpha planning',
          fileId: 'prior-chat-1',
          path: 'prior-chat-1',
          source: 'special',
          size: null,
          viaText: true,
        },
      ] satisfies MentionReference[],
    };
    await createMessageRequest('回顾一下上次结论', 'msg-zombie-chat', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).not.toHaveProperty('mention_references');
  });

  it('keeps non-text references (file browser / search / research) regardless of input text', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      ...baseState,
      mentionReferences: [
        {
          type: 'wiki_concept',
          label: 'ML',
          conceptName: '机器学习',
          source: 'special',
          size: null,
        },
        {
          type: 'workspace_file',
          label: '@main.py',
          path: 'src/main.py',
          source: 'workspace',
          size: null,
        },
      ] satisfies MentionReference[],
    };
    await createMessageRequest('继续分析', 'msg-non-text-refs', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).toMatchObject({
      mention_references: [
        { type: 'wiki_concept', concept_name: '机器学习' },
        { type: 'workspace_file', path: 'src/main.py' },
      ],
    });
  });

  it('parses a pasted @wiki: token inline into a wiki_concept reference', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = { ...baseState, mentionReferences: [] };
    await createMessageRequest('用知识库总结 @wiki:机器学习', 'msg-paste-wiki', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).toMatchObject({
      mention_references: [
        {
          type: 'wiki_concept',
          label: '@wiki:机器学习',
          concept_name: '机器学习',
        },
      ],
    });
  });
});
