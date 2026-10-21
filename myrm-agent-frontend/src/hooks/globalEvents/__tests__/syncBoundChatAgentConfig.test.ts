import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getAgentMock: vi.fn(),
  updateAgentConfigMock: vi.fn(),
  agentConfig: {
    agentId: 'agent-a',
    selectedSkillIds: ['old-skill'],
  } as { agentId?: string; selectedSkillIds: string[] } | null,
}));

vi.mock('@/services/agent', () => ({
  getAgent: mocks.getAgentMock,
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({
      agentConfig: mocks.agentConfig,
      updateAgentConfig: mocks.updateAgentConfigMock,
    }),
  },
}));

import { syncBoundChatAgentConfig } from '../syncBoundChatAgentConfig';

describe('syncBoundChatAgentConfig', () => {
  beforeEach(() => {
    mocks.getAgentMock.mockReset();
    mocks.updateAgentConfigMock.mockReset();
    mocks.agentConfig = { agentId: 'agent-a', selectedSkillIds: ['old-skill'] };
  });

  it('refreshes selectedSkillIds when chat session is bound to the same agent', async () => {
    mocks.getAgentMock.mockResolvedValue({ skill_ids: ['old-skill', 'new-skill'] });

    await syncBoundChatAgentConfig('agent-a');

    expect(mocks.getAgentMock).toHaveBeenCalledWith('agent-a', false);
    expect(mocks.updateAgentConfigMock).toHaveBeenCalledWith({
      selectedSkillIds: ['old-skill', 'new-skill'],
    });
  });

  it('skips when no chat agent is bound', async () => {
    mocks.agentConfig = null;

    await syncBoundChatAgentConfig('agent-a');

    expect(mocks.getAgentMock).not.toHaveBeenCalled();
    expect(mocks.updateAgentConfigMock).not.toHaveBeenCalled();
  });

  it('skips when bound agent differs from updated profile', async () => {
    mocks.agentConfig = { agentId: 'other-agent', selectedSkillIds: [] };

    await syncBoundChatAgentConfig('agent-a');

    expect(mocks.getAgentMock).not.toHaveBeenCalled();
  });
});
