/**
 * What stops a send before any request leaves: the processing lock that a failed validation must release, and the
 * preconditions that show a toast instead of sending.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { setGlobalTranslator } from '@/services/i18nToastService';
import * as api from '@/lib/api';
import { sendMessage, type ChatActionsMethods, type ChatActionsState } from '@/store/chat/messageRequest';
import useConfigStore from '@/store/useConfigStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';

const showI18nToastMock = vi.hoisted(() => vi.fn());
const resolveKanbanSendBlockReasonMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/i18nToastService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/i18nToastService')>();
  return {
    ...actual,
    showI18nToast: (...args: unknown[]) => showI18nToastMock(...args),
  };
});

vi.mock('@/lib/kanban/kanbanChatBoard', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/kanban/kanbanChatBoard')>();
  return {
    ...actual,
    resolveKanbanSendBlockReason: (...args: unknown[]) => resolveKanbanSendBlockReasonMock(...args),
  };
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

    await sendMessage(
      '请测试处理锁释放',
      'req-1',
      state,
      actions,
      () => 'req-1',
      () => 'req-1-alloc',
    );

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
    visionFrames: [],
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

    await sendMessage(
      'hello',
      'req-lock',
      baseState,
      baseActions,
      () => 'req-lock',
      () => 'req-lock-alloc',
    );

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
