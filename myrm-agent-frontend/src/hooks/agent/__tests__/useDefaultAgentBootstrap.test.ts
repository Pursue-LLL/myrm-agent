/**
 * @vitest-environment jsdom
 */
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AgentConfig } from '@/store/chat/types';

type StubAgent = { id: string; name: string; avatar_url?: string };

const mockChatState = vi.hoisted(() => ({ agentConfig: null as AgentConfig | null }));
const mockAgentState = vi.hoisted(() => ({
  agents: [] as StubAgent[],
  fetchAgents: vi.fn(),
  fetchAgent: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => ({
  default: { getState: () => mockChatState },
}));

vi.mock('@/store/useAgentStore', () => ({
  default: { getState: () => mockAgentState },
}));

vi.mock('@/lib/utils/agent-config', () => ({
  buildAgentConfig: (agent: StubAgent): AgentConfig => ({
    agentId: agent.id,
    agentName: agent.name,
    selectedSkillIds: ['skill-from-profile'],
    skillConfigs: {},
    selectedMcpNames: [],
    systemPrompt: 'profile prompt',
    useGlobalInstruction: true,
    autoRestoreDomains: [],
  }),
}));

import { useDefaultAgentBootstrap } from '../useDefaultAgentBootstrap';

const generalAgent: StubAgent = { id: 'builtin-general', name: 'General', avatar_url: 'icon:Sparkle' };

describe('useDefaultAgentBootstrap', () => {
  const setAgentConfig = vi.fn();

  beforeEach(() => {
    setAgentConfig.mockReset();
    mockChatState.agentConfig = null;
    mockAgentState.agents = [generalAgent];
    mockAgentState.fetchAgents.mockReset().mockResolvedValue(undefined);
    mockAgentState.fetchAgent.mockReset().mockResolvedValue(generalAgent);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('selects the built-in general agent with its preset fields when nothing is configured', async () => {
    renderHook(() => useDefaultAgentBootstrap(setAgentConfig));

    await waitFor(() => expect(setAgentConfig).toHaveBeenCalledTimes(1));
    expect(setAgentConfig).toHaveBeenCalledWith(
      expect.objectContaining({
        agentId: 'builtin-general',
        presetId: 'builtin-general',
        presetName: 'General',
        presetIcon: 'Sparkle',
        selectedSkillIds: ['skill-from-profile'],
      }),
    );
  });

  it('logs the failure and falls back to a minimal general config when the full agent cannot be loaded', async () => {
    const failure = new Error('network');
    mockAgentState.fetchAgent.mockRejectedValue(failure);
    const logged = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderHook(() => useDefaultAgentBootstrap(setAgentConfig));

    await waitFor(() => expect(setAgentConfig).toHaveBeenCalledTimes(1));
    expect(setAgentConfig).toHaveBeenCalledWith(
      expect.objectContaining({
        agentId: 'builtin-general',
        presetIcon: 'Sparkle',
        selectedSkillIds: [],
        systemPrompt: '',
      }),
    );
    expect(logged).toHaveBeenCalledWith('Failed to fetch full agent details for general', failure);
  });

  it.each<[string, Partial<AgentConfig>]>([
    ['an agent id', { agentId: 'custom-agent' }],
    ['a preset id', { presetId: 'builtin-coder' }],
    ['selected skills', { selectedSkillIds: ['skill-1'] }],
    ['selected MCP servers', { selectedMcpNames: ['github'] }],
    ['a system prompt', { systemPrompt: 'be brief' }],
    ['auto-restore domains', { autoRestoreDomains: ['example.com'] }],
  ])('keeps an existing configuration that has %s', async (_label, partial) => {
    mockChatState.agentConfig = {
      selectedSkillIds: [],
      skillConfigs: {},
      selectedMcpNames: [],
      systemPrompt: '',
      useGlobalInstruction: true,
      autoRestoreDomains: [],
      ...partial,
    };

    renderHook(() => useDefaultAgentBootstrap(setAgentConfig));
    await Promise.resolve();

    expect(mockAgentState.fetchAgents).not.toHaveBeenCalled();
    expect(setAgentConfig).not.toHaveBeenCalled();
  });

  it.each(['builtin-general', 'general'])(
    'accepts %s as the general agent, with the fallback icon when it has no avatar',
    async (id) => {
      mockAgentState.agents = [{ id, name: 'General' }];
      mockAgentState.fetchAgent.mockResolvedValue(mockAgentState.agents[0]);

      renderHook(() => useDefaultAgentBootstrap(setAgentConfig));

      await waitFor(() => expect(setAgentConfig).toHaveBeenCalledTimes(1));
      expect(setAgentConfig).toHaveBeenCalledWith(
        expect.objectContaining({ agentId: id, presetId: id, presetName: 'General', presetIcon: 'MessageCircle' }),
      );
    },
  );

  it('keeps the minimal general config when the full agent is not found', async () => {
    mockAgentState.fetchAgent.mockResolvedValue(null);

    renderHook(() => useDefaultAgentBootstrap(setAgentConfig));

    await waitFor(() => expect(setAgentConfig).toHaveBeenCalledTimes(1));
    expect(setAgentConfig).toHaveBeenCalledWith({
      agentId: 'builtin-general',
      selectedSkillIds: [],
      skillConfigs: {},
      selectedMcpNames: [],
      systemPrompt: '',
      useGlobalInstruction: true,
      autoRestoreDomains: [],
      presetId: 'builtin-general',
      presetName: 'General',
      presetIcon: 'Sparkle',
    });
  });

  it('logs the failure and selects nothing when the agent list cannot be loaded', async () => {
    const failure = new Error('offline');
    mockAgentState.fetchAgents.mockRejectedValue(failure);
    const logged = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderHook(() => useDefaultAgentBootstrap(setAgentConfig));

    await waitFor(() => expect(logged).toHaveBeenCalledWith(failure));
    expect(setAgentConfig).not.toHaveBeenCalled();
  });

  it('treats a stored configuration without any lists as not configured', async () => {
    // A configuration persisted by an older build can lack the list fields entirely.
    mockChatState.agentConfig = { useGlobalInstruction: true } as unknown as AgentConfig;

    renderHook(() => useDefaultAgentBootstrap(setAgentConfig));

    await waitFor(() => expect(setAgentConfig).toHaveBeenCalledTimes(1));
  });

  it('does nothing when the agent list has no general agent', async () => {
    mockAgentState.agents = [{ id: 'builtin-coder', name: 'Coder' }];

    renderHook(() => useDefaultAgentBootstrap(setAgentConfig));
    await waitFor(() => expect(mockAgentState.fetchAgents).toHaveBeenCalledTimes(1));

    expect(setAgentConfig).not.toHaveBeenCalled();
  });

  it('does not bootstrap again when the caller hands over a new setter', async () => {
    const replacement = vi.fn();
    const { rerender } = renderHook(({ setter }) => useDefaultAgentBootstrap(setter), {
      initialProps: { setter: setAgentConfig },
    });
    await waitFor(() => expect(setAgentConfig).toHaveBeenCalledTimes(1));

    rerender({ setter: replacement });
    await Promise.resolve();

    expect(mockAgentState.fetchAgents).toHaveBeenCalledTimes(1);
    expect(replacement).not.toHaveBeenCalled();
  });

  it('bootstraps only once across re-renders', async () => {
    const { rerender } = renderHook(() => useDefaultAgentBootstrap(setAgentConfig));
    await waitFor(() => expect(setAgentConfig).toHaveBeenCalledTimes(1));

    rerender();
    rerender();

    expect(mockAgentState.fetchAgents).toHaveBeenCalledTimes(1);
    expect(setAgentConfig).toHaveBeenCalledTimes(1);
  });
});
