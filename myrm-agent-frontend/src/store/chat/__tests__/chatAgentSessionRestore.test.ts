import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  finalizeAgentStreamTurn,
  restoreAgentConfigFromChat,
} from '@/store/chat/chatAgentSessionRestore';

const getChatDetailMock = vi.hoisted(() => vi.fn());
const fetchAgentMock = vi.hoisted(() => vi.fn());
const setAgentConfigMock = vi.hoisted(() => vi.fn());

const mockStore = vi.hoisted(() => ({
  chatId: 'chat-restore',
  actionMode: 'agent' as const,
  agentConfig: null as { agentId: string } | null,
  setAgentConfig: setAgentConfigMock,
}));

vi.mock('@/services/chat', () => ({
  getChatDetail: (...args: unknown[]) => getChatDetailMock(...args),
}));

vi.mock('@/store/useAgentStore', () => ({
  default: {
    getState: () => ({ fetchAgent: fetchAgentMock }),
  },
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => mockStore,
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

vi.mock('@/lib/utils/agentConfigMapper', () => ({
  buildAgentConfig: (agent: { id: string }) => ({ agentId: agent.id }),
}));

describe('chatAgentSessionRestore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStore.chatId = 'chat-restore';
    mockStore.actionMode = 'agent';
    mockStore.agentConfig = null;
    setAgentConfigMock.mockReset();
  });

  it('warns when fetchAgent rejects without throwing to callers', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    fetchAgentMock.mockRejectedValue(new Error('catalog offline'));

    await restoreAgentConfigFromChat('chat-restore', 'agent-1');

    expect(warnSpy).toHaveBeenCalledWith(
      '[MYRM-AGENT-RESTORE] restoreAgentConfigFromChat failed',
      expect.objectContaining({ chatId: 'chat-restore', agentId: 'agent-1' }),
    );
    expect(setAgentConfigMock).not.toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it('warns when fetchAgent returns empty catalog row', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    fetchAgentMock.mockResolvedValue(null);

    await restoreAgentConfigFromChat('chat-restore', 'agent-missing');

    expect(warnSpy).toHaveBeenCalledWith(
      '[MYRM-AGENT-RESTORE] fetchAgent returned empty',
      { chatId: 'chat-restore', agentId: 'agent-missing' },
    );
    warnSpy.mockRestore();
  });

  it('warns when finalize getChatDetail fails', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    getChatDetailMock.mockRejectedValue(new Error('api 503'));

    await finalizeAgentStreamTurn('chat-restore');

    expect(warnSpy).toHaveBeenCalledWith(
      '[MYRM-AGENT-RESTORE] finalizeAgentStreamTurn failed',
      expect.objectContaining({ chatId: 'chat-restore' }),
    );
    warnSpy.mockRestore();
  });
});
