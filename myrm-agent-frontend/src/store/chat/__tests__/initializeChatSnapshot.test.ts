import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AgentConfig, ChatState, Message } from '@/store/chat/types';
import {
  resetChatNavigationSnapshotsForTests,
  saveChatNavigationSnapshot,
} from '@/store/chat/chatNavigationSnapshotCache';
import { initializeChat } from '@/store/chat/messageManagement';

const getChatDetailMock = vi.hoisted(() => vi.fn());
const getMessagesMock = vi.hoisted(() => vi.fn());
const fetchAgentMock = vi.hoisted(() => vi.fn().mockResolvedValue(null));

vi.mock('@/store/useWorkspaceStore', () => ({
  default: {
    getState: () => ({ panes: [] }),
  },
}));

vi.mock('@/services/chat', () => ({
  getChatDetail: (...args: unknown[]) => getChatDetailMock(...args),
  getMessages: (...args: unknown[]) => getMessagesMock(...args),
  generateChatTitle: vi.fn(),
  updateChatTitle: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn().mockResolvedValue({ active: false }),
  ApiError: class ApiError extends Error {
    code: number;
    constructor(code: number) {
      super('api error');
      this.code = code;
    }
  },
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({ chatId: 'chat-a', agentConfig: null, setAgentConfig: vi.fn(), setSandboxMode: vi.fn() }),
  },
}));

vi.mock('@/store/skill', () => ({
  useSkillStore: {
    getState: () => ({
      fetchMarketSkills: vi.fn().mockResolvedValue(undefined),
      fetchLocalSkills: vi.fn().mockResolvedValue(undefined),
    }),
  },
}));

vi.mock('@/store/useAgentStore', () => ({
  default: {
    getState: () => ({ fetchAgent: (...args: unknown[]) => fetchAgentMock(...args) }),
  },
}));

vi.mock('@/store/useConfigStore', () => ({
  default: {
    getState: () => ({}),
  },
}));

vi.mock('@/store/useProjectStore', () => ({
  useProjectStore: {
    getState: () => ({ activeFilter: undefined }),
  },
}));

vi.mock('@/services/uploadController', () => ({
  abortCurrentUpload: vi.fn(),
}));

describe('initializeChat navigation snapshot', () => {
  beforeEach(() => {
    resetChatNavigationSnapshotsForTests();
    vi.clearAllMocks();
    getChatDetailMock.mockResolvedValue({
      chat: {
        actionMode: 'agent',
        compacted_summary: null,
        compacted_before_id: null,
        workspace_dir: null,
        session_loaded_skill_names: null,
        is_incognito: false,
        agent_id: null,
      },
    });
    getMessagesMock.mockResolvedValue({
      messages: [],
      has_more: false,
      next_cursor: null,
    });
  });

  it('restores agentConfig and model selection when switching back via sidebar snapshot', () => {
    const agentConfig = { agentId: 'agent-1', name: 'Test Agent' } as unknown as AgentConfig;
    const messages = [{ id: 'm1', role: 'user', content: 'hello' } as unknown as Message];

    saveChatNavigationSnapshot('chat-a', {
      messages,
      agentConfig,
      actionMode: 'deep_research',
      selectedModels: { base: 'gpt-4', vision: null, reasoning: null },
      hasUserSelectedModel: true,
      isMessagesLoaded: true,
      loading: false,
    });

    let currentState = {
      chatId: 'chat-b',
      messages: [] as Message[],
    } as unknown as ChatState;

    const actions = {
      setMessages: (updater: (state: ChatState) => void) => {
        const draft = { ...currentState } as ChatState;
        updater(draft);
        currentState = draft;
      },
      clearCurrentSessionMessageId: vi.fn(),
    };

    initializeChat('chat-a', currentState, actions as unknown as Parameters<typeof initializeChat>[2]);

    expect(currentState.chatId).toBe('chat-a');
    expect(currentState.agentConfig).toEqual(agentConfig);
    expect(currentState.actionMode).toBe('deep_research');
    expect(currentState.hasUserSelectedModel).toBe(true);
    expect(currentState.selectedModels).toEqual({ base: 'gpt-4', vision: null, reasoning: null });
    expect(currentState.isMessagesLoaded).toBe(false);
  });

  it('resets securityPreset to agent default when switching back via snapshot', () => {
    const agentConfig = {
      agentId: 'agent-1',
      name: 'Test Agent',
      defaultSecurityPreset: 'accept_edits',
    } as unknown as AgentConfig;
    const messages = [{ id: 'm1', role: 'user', content: 'hello' } as unknown as Message];

    saveChatNavigationSnapshot('chat-a', {
      messages,
      agentConfig,
      actionMode: 'agent',
      isMessagesLoaded: true,
      loading: false,
    });

    let currentState = {
      chatId: 'chat-b',
      messages: [] as Message[],
      securityPreset: 'explore',
    } as unknown as ChatState;

    const actions = {
      setMessages: (updater: (state: ChatState) => void) => {
        const draft = { ...currentState } as ChatState;
        updater(draft);
        currentState = draft;
      },
      clearCurrentSessionMessageId: vi.fn(),
    };

    initializeChat('chat-a', currentState, actions as unknown as Parameters<typeof initializeChat>[2]);

    expect(currentState.securityPreset).toBe('accept_edits');
  });

  it('falls back securityPreset to hitl on snapshot restore when agent has no default', () => {
    const agentConfig = { agentId: 'agent-1', name: 'Test Agent' } as unknown as AgentConfig;
    const messages = [{ id: 'm1', role: 'user', content: 'hello' } as unknown as Message];

    saveChatNavigationSnapshot('chat-a', {
      messages,
      agentConfig,
      actionMode: 'agent',
      isMessagesLoaded: true,
      loading: false,
    });

    let currentState = {
      chatId: 'chat-b',
      messages: [] as Message[],
      securityPreset: 'accept_edits',
    } as unknown as ChatState;

    const actions = {
      setMessages: (updater: (state: ChatState) => void) => {
        const draft = { ...currentState } as ChatState;
        updater(draft);
        currentState = draft;
      },
      clearCurrentSessionMessageId: vi.fn(),
    };

    initializeChat('chat-a', currentState, actions as unknown as Parameters<typeof initializeChat>[2]);

    expect(currentState.securityPreset).toBe('hitl');
  });

  it('keeps isMessagesLoaded true during silent background refresh', async () => {
    saveChatNavigationSnapshot('chat-a', {
      messages: [{ id: 'm1', role: 'user', content: 'cached' } as unknown as Message],
      isMessagesLoaded: true,
      loading: false,
    });

    let currentState = {
      chatId: 'chat-b',
      messages: [] as Message[],
      isMessagesLoaded: false,
      loading: false,
    } as unknown as ChatState;

    const actions = {
      setMessages: (updater: (state: ChatState) => void) => {
        const draft = { ...currentState } as ChatState;
        updater(draft);
        currentState = draft;
      },
      clearCurrentSessionMessageId: vi.fn(),
    };

    initializeChat('chat-a', currentState, actions as unknown as Parameters<typeof initializeChat>[2]);

    expect(currentState.isMessagesLoaded).toBe(true);

    await vi.waitFor(() => {
      expect(getChatDetailMock).toHaveBeenCalled();
    });

    expect(currentState.isMessagesLoaded).toBe(true);
  });

  it('preserves actionMode during silent background refresh after snapshot restore', async () => {
    saveChatNavigationSnapshot('chat-a', {
      messages: [{ id: 'm1', role: 'user', content: 'cached' } as unknown as Message],
      actionMode: 'deep_research',
      isMessagesLoaded: true,
      loading: false,
    });

    getChatDetailMock.mockResolvedValue({
      chat: {
        actionMode: 'agent',
        compacted_summary: null,
        compacted_before_id: null,
        workspace_dir: null,
        session_loaded_skill_names: null,
        is_incognito: false,
        agent_id: 'agent-server',
      },
    });

    let currentState = {
      chatId: 'chat-b',
      messages: [] as Message[],
      actionMode: 'agent' as ChatState['actionMode'],
      isMessagesLoaded: false,
      loading: false,
    } as unknown as ChatState;

    const actions = {
      setMessages: (updater: (state: ChatState) => void) => {
        const draft = { ...currentState } as ChatState;
        updater(draft);
        currentState = draft;
      },
      clearCurrentSessionMessageId: vi.fn(),
    };

    initializeChat('chat-a', currentState, actions as unknown as Parameters<typeof initializeChat>[2]);

    expect(currentState.actionMode).toBe('deep_research');

    await vi.waitFor(() => {
      expect(getChatDetailMock).toHaveBeenCalled();
    });

    expect(currentState.actionMode).toBe('deep_research');
    expect(fetchAgentMock).not.toHaveBeenCalled();
  });

  it('defers isMessagesLoaded until silent refresh completes for agent-bound snapshot', async () => {
    const agentConfig = {
      agentId: 'agent-1',
      name: 'Test Agent',
      defaultSecurityPreset: 'accept_edits',
    } as unknown as AgentConfig;

    saveChatNavigationSnapshot('chat-a', {
      messages: [{ id: 'm1', role: 'user', content: 'cached' } as unknown as Message],
      agentConfig,
      actionMode: 'agent',
      isMessagesLoaded: true,
      loading: false,
    });

    getChatDetailMock.mockResolvedValue({
      chat: {
        actionMode: 'agent',
        compacted_summary: null,
        compacted_before_id: null,
        workspace_dir: null,
        session_loaded_skill_names: null,
        is_incognito: false,
        agent_id: 'agent-1',
      },
    });

    let loadedBeforeRestore = false;
    fetchAgentMock.mockImplementation(async () => {
      loadedBeforeRestore = currentState.isMessagesLoaded === true;
      return agentConfig;
    });

    let currentState = {
      chatId: 'chat-b',
      messages: [] as Message[],
      isMessagesLoaded: false,
      loading: false,
    } as unknown as ChatState;

    const actions = {
      setMessages: (updater: (state: ChatState) => void) => {
        const draft = { ...currentState } as ChatState;
        updater(draft);
        currentState = draft;
      },
      clearCurrentSessionMessageId: vi.fn(),
    };

    initializeChat('chat-a', currentState, actions as unknown as Parameters<typeof initializeChat>[2]);

    expect(currentState.isMessagesLoaded).toBe(false);

    await vi.waitFor(() => {
      expect(currentState.isMessagesLoaded).toBe(true);
    });

    expect(loadedBeforeRestore).toBe(false);
    expect(fetchAgentMock).toHaveBeenCalledWith('agent-1');
  });
});
