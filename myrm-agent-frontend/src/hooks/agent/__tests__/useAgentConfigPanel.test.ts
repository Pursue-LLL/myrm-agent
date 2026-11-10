/**
 * The chat configuration panel's state and actions, against the real chat, skill, MCP, auth and agent stores.
 *
 * Real scenario: the user opens "details and fine-tuning" under the message box, reads which skills and MCP servers
 * the conversation uses, edits them in the dialog and, when no saved agent backs the conversation, saves the
 * combination as a new agent.
 */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AgentCreate } from '@/services/agent';
import type { AgentConfig } from '@/store/chat/types';
import { DEFAULT_ENABLED_BUILTIN_TOOLS } from '@/store/chat/types';
import { RiskBlockedError } from '@/store/chat/streamErrors';
import type { MCPServiceConfig } from '@/store/config/types';
import { useSkillStore } from '@/store/skill';
import type { Skill } from '@/store/skill/types';
import useAgentStore from '@/store/useAgentStore';
import useAuthStore from '@/store/useAuthStore';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import { deferred } from '@/test-utils/deferred';

const mocks = vi.hoisted(() => {
  const translators = new Map<string, (key: string) => string>();
  return {
    router: { push: vi.fn<(href: string) => void>() },
    toast: vi.fn(),
    createAgent: vi.fn<(data: AgentCreate) => Promise<{ id: string }>>(),
    bootstrap: vi.fn(),
    fetchMarketSkills: vi.fn<() => Promise<void>>(),
    fetchUserSkillConfig: vi.fn<() => Promise<void>>(),
    fetchLocalSkills: vi.fn<() => Promise<void>>(),
    fetchLocalSkillPaths: vi.fn<() => Promise<void>>(),
    fetchAgents: vi.fn<(forceRefresh?: boolean) => Promise<void>>(),
    // One translator per namespace for the whole file; the keys show which namespace each caller reads.
    translator: (namespace: string) => {
      let translate = translators.get(namespace);
      if (!translate) {
        translate = (key: string) => `${namespace}:${key}`;
        translators.set(namespace, translate);
      }
      return translate;
    },
  };
});

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => mocks.translator(namespace),
}));
vi.mock('next/navigation', () => ({ useRouter: () => mocks.router }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: mocks.toast }));
vi.mock('@/hooks/agent/useDefaultAgentBootstrap', () => ({ useDefaultAgentBootstrap: mocks.bootstrap }));
vi.mock('@/services/agent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/agent')>()),
  createAgent: mocks.createAgent,
}));

import { useAgentConfigPanel } from '../useAgentConfigPanel';

function skill(id: string, overrides: Partial<Skill> = {}): Skill {
  return {
    id,
    type: 'prebuilt',
    name: id,
    description: '',
    storage_path: '',
    version: '1.0.0',
    category: null,
    icon_url: null,
    tags: [],
    requires: { bins: [], env: [], config: [] },
    available: true,
    unavailable_reason: null,
    trust: 'builtin',
    author: null,
    homepage: null,
    always: false,
    model_invocable: true,
    user_invocable: true,
    primary_env: null,
    security: null,
    user_trusted: true,
    evolution_locked: false,
    has_upstream_update: false,
    verification_steps: [],
    eval_cases: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function mcp(name: string, enabled: boolean): MCPServiceConfig {
  return { name, type: 'sse', description: '', enabled };
}

function config(overrides: Partial<AgentConfig> = {}): AgentConfig {
  return {
    selectedSkillIds: [],
    selectedMcpNames: [],
    systemPrompt: '',
    useGlobalInstruction: true,
    ...overrides,
  };
}

const resolved = () => Promise.resolve();

beforeEach(() => {
  vi.resetAllMocks();
  for (const fetcher of [
    mocks.fetchMarketSkills,
    mocks.fetchUserSkillConfig,
    mocks.fetchLocalSkills,
    mocks.fetchLocalSkillPaths,
    mocks.fetchAgents,
  ]) {
    fetcher.mockImplementation(resolved);
  }
  useSkillStore.setState({
    marketSkills: [],
    localSkills: [],
    isSkillEnabled: () => true,
    fetchMarketSkills: mocks.fetchMarketSkills,
    fetchUserSkillConfig: mocks.fetchUserSkillConfig,
    fetchLocalSkills: mocks.fetchLocalSkills,
    fetchLocalSkillPaths: mocks.fetchLocalSkillPaths,
  });
  useAgentStore.setState({ fetchAgents: mocks.fetchAgents });
  useConfigStore.setState({ mcpConfigs: [] });
  useAuthStore.setState({ user: null });
  useChatStore.setState({
    agentConfig: null,
    actionMode: 'agent',
    isConfigPanelExpanded: true,
    currentBuiltinTools: [...DEFAULT_ENABLED_BUILTIN_TOOLS],
  });
});

afterEach(() => {
  window.history.replaceState({}, '', '/');
});

describe('useAgentConfigPanel: loading', () => {
  it('loads the skills, the local skill paths, the skill settings and the agent roster once on mount', () => {
    renderHook(() => useAgentConfigPanel());

    expect(mocks.fetchMarketSkills).toHaveBeenCalledTimes(1);
    expect(mocks.fetchUserSkillConfig).toHaveBeenCalledTimes(1);
    expect(mocks.fetchLocalSkills).toHaveBeenCalledTimes(1);
    expect(mocks.fetchLocalSkillPaths).toHaveBeenCalledTimes(1);
    expect(mocks.fetchAgents).toHaveBeenCalledTimes(1);
    expect(mocks.fetchAgents).toHaveBeenCalledWith();
  });

  it('loads nothing while an OAuth callback token is in the address', () => {
    window.history.replaceState({}, '', '/?token=abc');

    renderHook(() => useAgentConfigPanel());

    expect(mocks.fetchMarketSkills).not.toHaveBeenCalled();
    expect(mocks.fetchAgents).not.toHaveBeenCalled();
  });

  it('loads again for another signed-in user and not for an unrelated re-render', () => {
    const { rerender } = renderHook(() => useAgentConfigPanel());

    rerender();
    expect(mocks.fetchAgents).toHaveBeenCalledTimes(1);

    act(() => useAuthStore.setState({ user: { id: 'user-2', email: 'user-2@example.com' } }));
    expect(mocks.fetchAgents).toHaveBeenCalledTimes(2);
    expect(mocks.fetchMarketSkills).toHaveBeenCalledTimes(2);
  });

  it('selects the default agent through the shared bootstrap with the store setter', () => {
    renderHook(() => useAgentConfigPanel());

    expect(mocks.bootstrap).toHaveBeenCalledWith(useChatStore.getState().setAgentConfig);
  });

  it('refreshes the market and the local skills together and settles once both are done', async () => {
    const market = deferred<void>();
    mocks.fetchMarketSkills.mockReturnValue(market.promise);
    const { result } = renderHook(() => useAgentConfigPanel());
    mocks.fetchLocalSkills.mockClear();

    let settled = false;
    const refresh = result.current.refreshSkills().then(() => {
      settled = true;
    });
    await Promise.resolve();

    expect(mocks.fetchLocalSkills).toHaveBeenCalledTimes(1);
    expect(settled).toBe(false);
    market.resolve();
    await refresh;
    expect(settled).toBe(true);
  });
});

describe('useAgentConfigPanel: what the conversation uses', () => {
  it('offers the enabled skills of the market and the local ones, without skills the user cannot invoke', () => {
    useSkillStore.setState({
      marketSkills: [skill('market-on'), skill('market-off'), skill('market-hidden', { user_invocable: false })],
      localSkills: [skill('local-on')],
      isSkillEnabled: (id) => id !== 'market-off',
    });

    const { result } = renderHook(() => useAgentConfigPanel());

    expect(result.current.enabledSkills.map((item) => item.id)).toEqual(['market-on', 'local-on']);
  });

  it('shows the details of the selected skills and MCP servers in the order of their lists', () => {
    useSkillStore.setState({
      marketSkills: [skill('a'), skill('b'), skill('hidden', { user_invocable: false })],
      localSkills: [skill('c')],
    });
    useConfigStore.setState({ mcpConfigs: [mcp('docs', true), mcp('repo', false), mcp('mail', true)] });
    useChatStore.setState({
      agentConfig: config({ selectedSkillIds: ['c', 'a', 'hidden', 'gone'], selectedMcpNames: ['mail', 'repo'] }),
    });

    const { result } = renderHook(() => useAgentConfigPanel());

    expect(result.current.selectedSkillDetails.map((item) => item.id)).toEqual(['a', 'c']);
    expect(result.current.selectedMcpDetails.map((item) => item.name)).toEqual(['repo', 'mail']);
    expect(result.current.enabledMcps.map((item) => item.name)).toEqual(['docs', 'mail']);
  });

  it('has no selected details without a configuration', () => {
    const { result } = renderHook(() => useAgentConfigPanel());

    expect(result.current.selectedSkillDetails).toEqual([]);
    expect(result.current.selectedMcpDetails).toEqual([]);
  });

  it('passes the chat state through', () => {
    useChatStore.setState({ isConfigPanelExpanded: false, actionMode: 'fast' });

    const { result } = renderHook(() => useAgentConfigPanel());

    expect(result.current.isConfigPanelExpanded).toBe(false);
    expect(result.current.actionMode).toBe('fast');
    expect(result.current.currentBuiltinTools).toEqual(DEFAULT_ENABLED_BUILTIN_TOOLS);
  });
});

describe('useAgentConfigPanel: the welcome message and the edit dialog', () => {
  it('shows the typewriter welcome only when the mode changes to agent, until it completes', () => {
    useChatStore.setState({ actionMode: 'fast' });
    const { result } = renderHook(() => useAgentConfigPanel());
    expect(result.current.showTypewriter).toBe(false);

    act(() => useChatStore.setState({ actionMode: 'agent' }));
    expect(result.current.showTypewriter).toBe(true);

    act(() => result.current.handleTypewriterComplete());
    expect(result.current.showTypewriter).toBe(false);

    act(() => useChatStore.setState({ actionMode: 'fast' }));
    expect(result.current.showTypewriter).toBe(false);
    act(() => useChatStore.setState({ actionMode: 'agent' }));
    expect(result.current.showTypewriter).toBe(true);
  });

  it('stays quiet when the page already starts in agent mode', () => {
    const { result } = renderHook(() => useAgentConfigPanel());

    expect(result.current.showTypewriter).toBe(false);
  });

  it('opens the edit dialog on the clicked card and closes it on request', () => {
    const { result } = renderHook(() => useAgentConfigPanel());
    expect(result.current.editDialogOpen).toBe(false);
    expect(result.current.editDialogType).toBe('skills');

    act(() => result.current.handleCardClick('instruction'));
    expect(result.current.editDialogOpen).toBe(true);
    expect(result.current.editDialogType).toBe('instruction');

    act(() => result.current.setEditDialogOpen(false));
    expect(result.current.editDialogOpen).toBe(false);
  });

  it('saves an edited instruction as a conversation-level rewrite and keeps the chosen built-in tools', () => {
    useChatStore.setState({ agentConfig: config({ agentId: 'agent-1', systemPrompt: 'saved' }) });
    const { result } = renderHook(() => useAgentConfigPanel());

    act(() => result.current.handleSaveConfig({ systemPrompt: 'edited', enabledBuiltinTools: ['browser'] }));

    const saved = useChatStore.getState().agentConfig;
    expect(saved).toMatchObject({ agentId: 'agent-1', systemPrompt: 'edited', systemPromptEdited: true });
    expect(useChatStore.getState().currentBuiltinTools).toEqual(['browser']);
  });

  it('builds a configuration from the saved parts when the conversation had none', () => {
    const { result } = renderHook(() => useAgentConfigPanel());

    act(() => result.current.handleSaveConfig({ selectedSkillIds: ['skill-1'] }));

    expect(useChatStore.getState().agentConfig).toMatchObject({
      selectedSkillIds: ['skill-1'],
      selectedMcpNames: [],
      systemPrompt: '',
      useGlobalInstruction: true,
    });
  });
});

describe('useAgentConfigPanel: saving the combination as a new agent', () => {
  const fullConfig = config({
    selectedSkillIds: ['skill-1'],
    skillConfigs: { 'skill-1': { is_core: true, instance_name: 'main' } },
    selectedMcpNames: ['docs'],
    mcpToolSelections: { docs: ['search'] },
    systemPrompt: 'You are precise.',
    autoRestoreDomains: ['example.com'],
    browserSource: 'extension',
    dialogPolicy: 'auto_dismiss',
    sessionRecording: 'on_failure',
    suggestionPrompts: ['Ask me anything'],
    memoryDecayProfile: 'fast',
    memoryExtractionPreset: 'research',
    modelSelection: { providerId: 'p1', model: 'm1' },
    fallbackModelSelection: { providerId: 'p2', model: 'm2' },
    safetyFallbackModelSelection: { providerId: 'p3', model: 'm3' },
  });

  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    mocks.createAgent.mockResolvedValue({ id: 'new-agent' });
  });

  it('creates the agent from the whole configuration and opens it in the settings', async () => {
    useChatStore.setState({ agentConfig: fullConfig, currentBuiltinTools: ['web_search', 'kanban'] });
    const { result } = renderHook(() => useAgentConfigPanel());

    await act(() => result.current.handleSaveAsNewAgent());

    expect(mocks.createAgent).toHaveBeenCalledTimes(1);
    expect(mocks.createAgent).toHaveBeenCalledWith({
      name: 'agent:newAgentName',
      description: '',
      system_prompt: 'You are precise.',
      mcp_ids: ['docs'],
      mcp_tool_selections: { docs: ['search'] },
      skill_ids: ['skill-1'],
      skill_configs: { 'skill-1': { is_core: true, instance_name: 'main' } },
      enabled_builtin_tools: ['web_search', 'kanban'],
      auto_restore_domains: ['example.com'],
      browser_source: 'extension',
      dialog_policy: 'auto_dismiss',
      session_recording: 'on_failure',
      suggestion_prompts: ['Ask me anything'],
      model_selection: {
        providerId: 'p1',
        model: 'm1',
        fallbackProviderId: 'p2',
        fallbackModel: 'm2',
        safetyFallbackProviderId: 'p3',
        safetyFallbackModel: 'm3',
      },
      memory_decay_profile: 'fast',
      memory_extraction_preset: 'research',
    });
    expect(mocks.toast).toHaveBeenCalledWith({ title: 'agent:createSuccess' });
    expect(mocks.router.push).toHaveBeenCalledWith('/settings/agents?agentId=new-agent');
    expect(result.current.isSavingAgent).toBe(false);
  });

  it('sends defaults for the parts the configuration leaves out and no model without a primary model', async () => {
    useChatStore.setState({
      agentConfig: config({
        selectedSkillIds: ['skill-1'],
        fallbackModelSelection: { providerId: 'p2', model: 'm2' },
      }),
    });
    const { result } = renderHook(() => useAgentConfigPanel());

    await act(() => result.current.handleSaveAsNewAgent());

    expect(mocks.createAgent).toHaveBeenCalledWith({
      name: 'agent:newAgentName',
      description: '',
      system_prompt: '',
      mcp_ids: [],
      skill_ids: ['skill-1'],
      skill_configs: {},
      enabled_builtin_tools: DEFAULT_ENABLED_BUILTIN_TOOLS,
      auto_restore_domains: [],
      suggestion_prompts: null,
      model_selection: null,
      memory_decay_profile: undefined,
      memory_extraction_preset: undefined,
    });
  });

  it('leaves the fallback models undefined when only the primary model is configured', async () => {
    useChatStore.setState({
      agentConfig: config({ systemPrompt: 'x', modelSelection: { providerId: 'p1', model: 'm1' } }),
    });
    const { result } = renderHook(() => useAgentConfigPanel());

    await act(() => result.current.handleSaveAsNewAgent());

    const [payload] = mocks.createAgent.mock.calls[0];
    expect(payload.model_selection).toStrictEqual({
      providerId: 'p1',
      model: 'm1',
      fallbackProviderId: undefined,
      fallbackModel: undefined,
      safetyFallbackProviderId: undefined,
      safetyFallbackModel: undefined,
    });
  });

  it.each([
    ['no configuration at all', null, false],
    ['an empty configuration', config(), false],
    ['an instruction of blanks only', config({ systemPrompt: '   \n ' }), false],
    ['a selected skill', config({ selectedSkillIds: ['skill-1'] }), true],
    ['a selected MCP server', config({ selectedMcpNames: ['docs'] }), true],
    ['an instruction', config({ systemPrompt: 'Be brief.' }), true],
    ['restore domains alone', config({ autoRestoreDomains: ['example.com'] }), true],
  ])('reports that %s is worth saving as an agent: %s', (_label, agentConfig, expected) => {
    useChatStore.setState({ agentConfig });

    const { result } = renderHook(() => useAgentConfigPanel());

    expect(result.current.hasSavableConfig).toBe(expected);
  });

  it.each([
    ['no configuration at all', null],
    ['an empty configuration', config()],
    ['an instruction of blanks only', config({ systemPrompt: '   \n ' })],
  ])('tells the user there is nothing to save for %s', async (_label, agentConfig) => {
    useChatStore.setState({ agentConfig });
    const { result } = renderHook(() => useAgentConfigPanel());

    await act(() => result.current.handleSaveAsNewAgent());

    expect(mocks.toast).toHaveBeenCalledWith({ title: 'agent:configPanel.noConfig', variant: 'destructive' });
    expect(mocks.createAgent).not.toHaveBeenCalled();
    expect(mocks.router.push).not.toHaveBeenCalled();
  });

  it('counts restore domains alone as a configuration', async () => {
    useChatStore.setState({ agentConfig: config({ autoRestoreDomains: ['example.com'] }) });
    const { result } = renderHook(() => useAgentConfigPanel());

    await act(() => result.current.handleSaveAsNewAgent());

    expect(mocks.createAgent).toHaveBeenCalledTimes(1);
  });

  it('ignores a second request while the first one is still saving', async () => {
    const creation = deferred<{ id: string }>();
    mocks.createAgent.mockReturnValue(creation.promise);
    useChatStore.setState({ agentConfig: fullConfig });
    const { result } = renderHook(() => useAgentConfigPanel());

    let first: Promise<void> = Promise.resolve();
    act(() => {
      first = result.current.handleSaveAsNewAgent();
    });
    expect(result.current.isSavingAgent).toBe(true);

    await act(() => result.current.handleSaveAsNewAgent());
    expect(mocks.createAgent).toHaveBeenCalledTimes(1);

    await act(async () => {
      creation.resolve({ id: 'new-agent' });
      await first;
    });
    expect(result.current.isSavingAgent).toBe(false);
  });

  it('tells the user when the creation fails and lets them try again', async () => {
    mocks.createAgent.mockRejectedValueOnce(new Error('server down'));
    useChatStore.setState({ agentConfig: fullConfig });
    const { result } = renderHook(() => useAgentConfigPanel());

    await act(() => result.current.handleSaveAsNewAgent());

    expect(mocks.toast).toHaveBeenCalledWith({ title: 'agent:operationFailed', variant: 'destructive' });
    expect(mocks.router.push).not.toHaveBeenCalled();
    expect(result.current.isSavingAgent).toBe(false);

    await act(() => result.current.handleSaveAsNewAgent());
    expect(mocks.router.push).toHaveBeenCalledWith('/settings/agents?agentId=new-agent');
  });

  it('adds no failure toast of its own when a risk rule held the text and already told the user', async () => {
    mocks.createAgent.mockRejectedValueOnce(new RiskBlockedError());
    useChatStore.setState({ agentConfig: fullConfig });
    const { result } = renderHook(() => useAgentConfigPanel());

    await act(() => result.current.handleSaveAsNewAgent());

    expect(mocks.toast).not.toHaveBeenCalled();
    expect(mocks.router.push).not.toHaveBeenCalled();
    expect(result.current.isSavingAgent).toBe(false);
  });
});
