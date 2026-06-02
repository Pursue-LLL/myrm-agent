import { describe, it, expect, vi } from 'vitest';
import { setGlobalTranslator } from '@/services/i18nToastService';
import * as api from '@/lib/api';
import { createAISearchStream } from '@/services/chat';
import { normalizeLocaleForBackend } from '@/lib/utils/localeUtils';
import type { AgentConfig } from '@/store/chat/types';
import {
  createMessageRequest,
  resolveEffectiveAgentId,
  sendMessage,
  type ChatActionsMethods,
  type ChatActionsState,
} from '@/store/chat/messageRequest';
import useConfigStore from '@/store/useConfigStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';

vi.mock('@/services/chat', () => ({
  createAISearchStream: vi.fn(async () => new Response('', { status: 200 })),
}));

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

  it('should return builtin-deep-search in fast mode with deep depth', () => {
    expect(resolveEffectiveAgentId('fast', baseAgentConfig, 'deep')).toBe('builtin-deep-search');
  });

  it('should return builtin-fast-search in fast mode when depth is undefined', () => {
    expect(resolveEffectiveAgentId('fast', baseAgentConfig)).toBe('builtin-fast-search');
  });

  it('should not inject an agent id in non-agent non-fast mode', () => {
    expect(resolveEffectiveAgentId('deep_research', baseAgentConfig)).toBeUndefined();
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
      isGoalMode: false,
      goalBudgetTokens: null,
      goalAcceptanceCriteria: null,
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
      isGoalMode: false,
      goalBudgetTokens: null,
      goalAcceptanceCriteria: null,
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

    await sendMessage('请测试处理锁释放', 'req-1', state, actions, () => 'req-1');

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
