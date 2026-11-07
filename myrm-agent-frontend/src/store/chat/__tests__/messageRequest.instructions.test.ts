import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createAISearchStream } from '@/services/chat';
import type { AgentConfig } from '@/store/chat/types';
import { createMessageRequest, type ChatActionsState } from '@/store/chat/messageRequest';
import useAuthStore from '@/store/useAuthStore';
import useCompanionStore from '@/store/useCompanionStore';
import useConfigStore from '@/store/useConfigStore';

vi.mock('@/services/chat', () => ({
  createAISearchStream: vi.fn(async () => new Response('', { status: 200 })),
}));

const GLOBAL_INSTRUCTION = 'Global: answer briefly.';
const AGENT_PERSONA = 'Persona: speak like a pirate.';
const CHAT_LEVEL_PROMPT = 'Chat-level: be formal.';

const makeState = (overrides: Record<string, unknown> = {}) =>
  ({
    chatId: 'chat-instructions',
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

const makeAgentConfig = (overrides: Partial<AgentConfig> = {}): AgentConfig => ({
  agentId: 'custom-1',
  selectedSkillIds: [],
  selectedMcpNames: [],
  systemPrompt: AGENT_PERSONA,
  useGlobalInstruction: true,
  ...overrides,
});

const sentBody = async (state: ChatActionsState) => {
  const stream = vi.mocked(createAISearchStream);
  stream.mockClear();
  await createMessageRequest('hello', 'msg-instructions', state, null);
  const [body] = stream.mock.calls[0] ?? [];
  if (!body) {
    throw new Error('the request was not sent');
  }
  return body;
};

describe('createMessageRequest - instructions', () => {
  beforeEach(() => {
    useConfigStore.setState({ systemInstructions: GLOBAL_INSTRUCTION });
    useAuthStore.setState({ user: { id: 'user-1', email: 'user-1@example.com' } });
    useCompanionStore.setState({ enabled: false });
  });

  it('leaves the agent system prompt to the server: user_instructions carries the global instruction only', async () => {
    const body = await sentBody(makeState({ agentConfig: makeAgentConfig() }));

    expect(body.user_instructions).toBe(GLOBAL_INSTRUCTION);
    expect(body.agent_config).not.toHaveProperty('system_prompt');
  });

  it('sends nothing when the agent opts out of the global instruction and has no companion', async () => {
    const body = await sentBody(makeState({ agentConfig: makeAgentConfig({ useGlobalInstruction: false }) }));

    expect(body).not.toHaveProperty('user_instructions');
  });

  it('keeps the global instruction when no agent is configured', async () => {
    const body = await sentBody(makeState());

    expect(body.user_instructions).toBe(GLOBAL_INSTRUCTION);
  });

  it('keeps the global instruction in fast mode and sends no agent_config', async () => {
    const body = await sentBody(makeState({ actionMode: 'fast', agentConfig: makeAgentConfig() }));

    expect(body.user_instructions).toBe(GLOBAL_INSTRUCTION);
    expect(body).not.toHaveProperty('agent_config');
  });

  it('sends the prompt as a chat-level replacement once the chat rewrote it, never inside user_instructions', async () => {
    const body = await sentBody(
      makeState({ agentConfig: makeAgentConfig({ systemPrompt: CHAT_LEVEL_PROMPT, systemPromptEdited: true }) }),
    );

    expect(body.agent_config).toHaveProperty('system_prompt', CHAT_LEVEL_PROMPT);
    expect(body.user_instructions).toBe(GLOBAL_INSTRUCTION);
  });

  it('sends an empty chat-level prompt so the saved prompt can be cleared for this chat', async () => {
    const body = await sentBody(
      makeState({ agentConfig: makeAgentConfig({ systemPrompt: '', systemPromptEdited: true }) }),
    );

    expect(body.agent_config).toHaveProperty('system_prompt', '');
  });

  it('appends the companion intro after the global instruction', async () => {
    useCompanionStore.setState({ enabled: true, muted: false, nameOverride: 'Pip' });

    const body = await sentBody(makeState({ agentConfig: makeAgentConfig() }));

    expect(body.user_instructions).toContain(`${GLOBAL_INSTRUCTION}\n# Companion\n`);
    expect(body.user_instructions).toContain('Pip');
    expect(body.user_instructions).not.toContain(AGENT_PERSONA);
  });
});
