/**
 * How the mentions typed in the input become the references of the request: a reference lives only while its
 * token is in the text, and the references that are not text stay.
 */
import { describe, it, expect, vi } from 'vitest';
import { createAISearchStream } from '@/services/chat';
import { expectDefined } from '@/test-utils/expectDefined';
import type { AgentConfig, MentionReference } from '@/store/chat/types';
import { createMessageRequest, type ChatActionsState } from '@/store/chat/messageRequest';
import { inSessionMentionDeduplicator } from '../inSessionMentionDeduplicator';

vi.mock('@/services/chat', () => ({
  createAISearchStream: vi.fn(async () => new Response('', { status: 200 })),
}));

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

  it('forwards artifact_range selection content and range tag to the protocol payload', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const state = {
      ...baseState,
      mentionReferences: [
        {
          type: 'artifact_range',
          label: 'sales.xlsx',
          artifactId: 'art-001',
          sheetName: 'Sheet1',
          range: 'Sheet1!B2:F10',
          source: 'generated',
          size: 42,
          content: 'Region: North, Q1: 1200, Q2: 1350',
        } satisfies MentionReference,
      ],
    };
    await createMessageRequest('把这个区域做成图表', 'msg-artifact-range', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).toMatchObject({
      mention_references: [
        {
          type: 'artifact_range',
          label: 'sales.xlsx',
          range: 'Sheet1!B2:F10',
          content: 'Region: North, Q1: 1200, Q2: 1350',
        },
      ],
    });
    expect(requestBody.mention_references?.[0]).not.toHaveProperty('artifact_id');
  });

  it('truncates oversized artifact_range content to the inline budget with a marker', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const oversized = 'x'.repeat(40_000);
    const state = {
      ...baseState,
      mentionReferences: [
        {
          type: 'artifact_range',
          label: 'huge.xlsx',
          range: 'Sheet1!A1:ZZ9999',
          source: 'generated',
          size: oversized.length,
          content: oversized,
        } satisfies MentionReference,
      ],
    };
    await createMessageRequest('总结这个选区', 'msg-artifact-range-trunc', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).toMatchObject({
      mention_references: [
        {
          type: 'artifact_range',
          label: 'huge.xlsx',
          content: expect.stringContaining('…[truncated]'),
        },
      ],
    });
    const sentContent = (requestBody.mention_references as Array<{ content?: string }>)[0]?.content;
    expectDefined(sentContent, 'truncated selection content');
    expect(sentContent.length).toBe(32_013); // 32_000 chars + "\n…[truncated]" suffix
  });

  it('attaches auto_moa_reasoning and auto_moa_preset_id when agentConfig auto_on_reasoning is enabled', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValueOnce(new Response('', { status: 200 }));

    const customAgentConfig: AgentConfig = {
      agentId: 'agent-moa',
      agentName: 'MoA Agent',
      systemPrompt: '',
      useGlobalInstruction: true,
      selectedSkillIds: [],
      selectedMcpNames: [],
      engineParams: {
        moa_overlay: {
          auto_on_reasoning: true,
        },
      },
    };

    const state = { ...baseState, agentConfig: customAgentConfig, mentionReferences: [] };
    await createMessageRequest('复杂数学定理证明', 'msg-moa-auto', state, null);

    const [requestBody] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(requestBody).toMatchObject({
      auto_moa_reasoning: true,
    });
  });

  it('deduplicates in-session file mentions by marking fresh files and omitting content on subsequent turns', async () => {
    const createAISearchStreamMock = createAISearchStream as ReturnType<typeof vi.fn>;
    createAISearchStreamMock.mockClear();
    createAISearchStreamMock.mockResolvedValue(new Response('', { status: 200 }));

    const testChatId = 'chat-dedup-test';
    inSessionMentionDeduplicator.clearSession(testChatId);

    const fileRef: MentionReference = {
      type: 'workspace_file',
      label: '@src/config.ts',
      path: 'src/config.ts',
      source: 'workspace',
      size: 100,
      content: 'export const CONFIG = 42;',
    };

    const state = {
      ...baseState,
      chatId: testChatId,
      mentionReferences: [fileRef],
    };

    // First turn: fresh file, content is retained and file is registered into deduplicator
    await createMessageRequest('首轮提问 @src/config.ts', 'msg-turn-1', state, null);

    const [body1] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(body1.mention_references).toEqual([
      expect.objectContaining({
        type: 'workspace_file',
        path: 'src/config.ts',
        content: 'export const CONFIG = 42;',
      }),
    ]);
    expect(inSessionMentionDeduplicator.isPathInjected(testChatId, 'src/config.ts')).toBe(true);

    // Second turn: same file mentioned again in the same session. Full text content is omitted to prevent context bloat
    createAISearchStreamMock.mockClear();
    await createMessageRequest('次轮提问再次 @src/config.ts', 'msg-turn-2', state, null);

    const [body2] = createAISearchStreamMock.mock.calls[0] ?? [];
    expect(body2.mention_references).toEqual([
      expect.objectContaining({
        type: 'workspace_file',
        path: 'src/config.ts',
      }),
    ]);
    expect((body2.mention_references as Array<{ content?: string }>)[0]?.content).toBeUndefined();
  });
});
