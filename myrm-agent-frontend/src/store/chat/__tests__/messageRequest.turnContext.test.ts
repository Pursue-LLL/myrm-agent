/**
 * What a turn runs as and where it runs: the goal budget, the active MoA preset or pending workflow template, and
 * the workspace folder of the first turn.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createAISearchStream } from '@/services/chat';
import { createMessageRequest, type ChatActionsState } from '@/store/chat/messageRequest';
import useChatStore from '@/store/useChatStore';

vi.mock('@/services/chat', () => ({
  createAISearchStream: vi.fn(async () => new Response('', { status: 200 })),
}));

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
    visionFrames: [],
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
      visionFrames: [],
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

describe('messageRequest - first-turn workspace', () => {
  it('sends the folder the viewer picked so the very first turn runs in it', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));
    const previous = useChatStore.getState().workspaceDir;
    useChatStore.setState({ workspaceDir: '/work/reports' });

    try {
      await createMessageRequest(
        'summarise the invoices',
        'msg-workspace',
        { ...useChatStore.getState(), chatId: 'chat-first-turn' } as unknown as ChatActionsState,
        null,
      );

      const [requestBody] = createAISearchStreamMock.mock.calls.at(-1) ?? [];
      expect(requestBody).toMatchObject({ workspace_dir: '/work/reports' });
    } finally {
      useChatStore.setState({ workspaceDir: previous });
    }
  });

  it('omits the field when no folder is bound, so the server keeps resolving the session folder', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));
    const previous = useChatStore.getState().workspaceDir;
    useChatStore.setState({ workspaceDir: null });

    try {
      await createMessageRequest(
        'just a question',
        'msg-no-workspace',
        { ...useChatStore.getState(), chatId: 'chat-first-turn' } as unknown as ChatActionsState,
        null,
      );

      const [requestBody] = createAISearchStreamMock.mock.calls.at(-1) ?? [];
      expect(requestBody).not.toHaveProperty('workspace_dir');
    } finally {
      useChatStore.setState({ workspaceDir: previous });
    }
  });
});
