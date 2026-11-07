import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AgentConfig } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { createSaveConfigHandler } from '../handlers';

const makeAgentConfig = (overrides: Partial<AgentConfig> = {}): AgentConfig => ({
  agentId: 'agent-1',
  selectedSkillIds: [],
  selectedMcpNames: [],
  systemPrompt: 'Saved prompt',
  useGlobalInstruction: true,
  ...overrides,
});

const setup = (agentConfig: AgentConfig | null) => {
  const updateAgentConfig = vi.fn();
  const setAgentConfig = vi.fn();
  const save = createSaveConfigHandler(agentConfig, updateAgentConfig, setAgentConfig, vi.fn());
  return { save, updateAgentConfig, setAgentConfig };
};

describe('createSaveConfigHandler - chat-level prompt edit', () => {
  it('marks a rewritten prompt as an edit of this chat', () => {
    const { save, updateAgentConfig } = setup(makeAgentConfig());

    save({ systemPrompt: 'New prompt', useGlobalInstruction: true });

    expect(updateAgentConfig).toHaveBeenCalledWith({
      systemPrompt: 'New prompt',
      useGlobalInstruction: true,
      systemPromptEdited: true,
    });
  });

  it('does not treat an untouched prompt as an edit when the dialog is saved again', () => {
    const { save, updateAgentConfig } = setup(makeAgentConfig());

    save({ systemPrompt: 'Saved prompt', useGlobalInstruction: false });

    expect(updateAgentConfig).toHaveBeenCalledWith({ systemPrompt: 'Saved prompt', useGlobalInstruction: false });
  });

  it('does not treat a save without a prompt as an edit', () => {
    const { save, updateAgentConfig } = setup(makeAgentConfig());

    save({ selectedSkillIds: ['skill-a'] });

    expect(updateAgentConfig).toHaveBeenCalledWith({ selectedSkillIds: ['skill-a'] });
  });

  it('marks the first config created from a typed prompt as an edit', () => {
    const { save, setAgentConfig } = setup(null);

    save({ systemPrompt: 'Typed prompt' });

    expect(setAgentConfig).toHaveBeenCalledWith(
      expect.objectContaining({ systemPrompt: 'Typed prompt', systemPromptEdited: true }),
    );
  });

  it('does not mark the first config as an edit when no prompt was typed', () => {
    const { save, setAgentConfig } = setup(null);

    save({ selectedSkillIds: ['skill-a'] });

    expect(setAgentConfig).toHaveBeenCalledWith(
      expect.objectContaining({ systemPrompt: '', systemPromptEdited: false }),
    );
  });
});

describe('chat store - chat-level prompt edit', () => {
  afterEach(() => {
    useChatStore.setState({ agentConfig: null });
  });

  it('drops the edit when another agent is selected', () => {
    const { setAgentConfig } = useChatStore.getState();
    setAgentConfig(makeAgentConfig({ systemPrompt: 'Chat-level prompt', systemPromptEdited: true }));
    expect(useChatStore.getState().agentConfig?.systemPromptEdited).toBe(true);

    setAgentConfig(makeAgentConfig({ agentId: 'agent-2' }));

    expect(useChatStore.getState().agentConfig?.agentId).toBe('agent-2');
    expect(useChatStore.getState().agentConfig?.systemPromptEdited).toBeUndefined();
  });
});
