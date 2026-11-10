/**
 * The advanced settings at the bottom of the configuration panel: direct delegation to an external agent, the
 * just-in-time team blueprints and the two memory selectors, against the real chat store and the real select.
 *
 * Real scenario: the user opens "details and fine-tuning", sends the conversation to a CLI agent, lets a research
 * squad work on it or makes the agent forget faster; each choice must reach the session configuration the next
 * message is sent with.
 */
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ExternalAgentConfig } from '@/services/config';
import useChatStore from '@/store/useChatStore';
import { expectNonNull } from '@/test-utils/expectDefined';

const mocks = vi.hoisted(() => {
  const noop = () => undefined;
  return {
    externalAgents: undefined as { agents: ExternalAgentConfig[] } | undefined,
    panel: {
      isSavingAgent: false,
      editDialogOpen: false,
      editDialogType: 'skills',
      showTypewriter: false,
      hasSavableConfig: false,
      agentConfig: null,
      actionMode: 'agent',
      isConfigPanelExpanded: true,
      enabledSkills: [],
      enabledMcps: [],
      selectedSkillDetails: [],
      selectedMcpDetails: [],
      currentBuiltinTools: [],
      setEditDialogOpen: noop,
      handleCardClick: noop,
      handleSaveConfig: noop,
      handleSaveAsNewAgent: noop,
      handleTypewriterComplete: noop,
      refreshSkills: noop,
    },
  };
});

vi.mock('@/hooks/agent/useAgentConfigPanel', () => ({ useAgentConfigPanel: () => mocks.panel }));
vi.mock('@/hooks/chat/useChatTurnPrewarm', () => ({
  useChatTurnPrewarm: () => ({ triggerPrewarm: () => Promise.resolve() }),
}));
vi.mock('@/services/config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/config')>()),
  getConfigSyncManager: () => ({ get: () => mocks.externalAgents }),
}));
vi.mock('../AgentConfigCards', () => ({ default: () => null }));
vi.mock('../TypewriterWelcome', () => ({ default: () => null }));
vi.mock('../AgentConfigEditDialog', () => ({ default: () => null }));

import AgentConfigPanel from '../AgentConfigPanel';
import { BLUEPRINT_TEMPLATES } from '../blueprintTemplates';

type User = ReturnType<typeof userEvent.setup>;

function externalAgent(name: string, enabled: boolean): ExternalAgentConfig {
  return { name, type: 'cli', command: name, enabled, permissionMode: 'ask' };
}

/** Opens the select that currently shows `shown` and picks `option` from its list. */
async function pick(user: User, shown: string, option: string) {
  const trigger = screen.getByText(shown).closest('button');
  expectNonNull(trigger, `the select showing "${shown}"`);
  await user.click(trigger);
  await user.click(await screen.findByRole('option', { name: option }));
}

async function optionsOf(user: User, shown: string): Promise<string[]> {
  const trigger = screen.getByText(shown).closest('button');
  expectNonNull(trigger, `the select showing "${shown}"`);
  await user.click(trigger);
  const names = (await screen.findAllByRole('option')).map((item) => item.textContent ?? '');
  await user.keyboard('{Escape}');
  return names;
}

const sessionConfig = () => useChatStore.getState().agentConfig;

function configureTeam(ephemeralSubagents: Record<string, unknown>) {
  useChatStore.setState({
    agentConfig: {
      selectedSkillIds: [],
      selectedMcpNames: [],
      systemPrompt: '',
      useGlobalInstruction: true,
      ephemeralSubagents,
    },
  });
}

// The panel is memoized: a re-render needs a changed prop to read the hook state again.
let rerenderCount = 0;
function refresh(rerender: (ui: ReactElement) => void) {
  rerenderCount += 1;
  rerender(<AgentConfigPanel className={`render-${rerenderCount}`} />);
}

beforeEach(() => {
  mocks.externalAgents = undefined;
  mocks.panel.isConfigPanelExpanded = true;
  useChatStore.setState({ agentConfig: null });
});

describe('direct delegation to an external agent', () => {
  it('is not offered when no external agent is enabled', () => {
    mocks.externalAgents = { agents: [externalAgent('codex', false)] };

    render(<AgentConfigPanel />);

    expect(screen.queryByText('directDelegate')).toBeNull();
  });

  it('is not offered before the external agents were configured at all', () => {
    render(<AgentConfigPanel />);

    expect(screen.queryByText('directDelegate')).toBeNull();
  });

  it('lists the enabled agents after the off entry and routes the conversation to the chosen one', async () => {
    mocks.externalAgents = { agents: [externalAgent('claude', true), externalAgent('codex', false)] };
    const user = userEvent.setup();
    render(<AgentConfigPanel />);

    expect(screen.getByText('directDelegate')).toBeInTheDocument();
    expect(await optionsOf(user, 'directDelegateOff')).toEqual(['directDelegateOff', 'claude']);

    await pick(user, 'directDelegateOff', 'claude');

    expect(sessionConfig()?.forceExternalAgent).toBe('claude');
  });

  it('shows the routed agent and clears the routing with the off entry', async () => {
    mocks.externalAgents = { agents: [externalAgent('claude', true)] };
    useChatStore.setState({
      agentConfig: {
        selectedSkillIds: [],
        selectedMcpNames: [],
        systemPrompt: '',
        useGlobalInstruction: true,
        forceExternalAgent: 'claude',
      },
    });
    const user = userEvent.setup();
    render(<AgentConfigPanel />);

    await pick(user, 'claude', 'directDelegateOff');

    expect(sessionConfig()?.forceExternalAgent).toBeUndefined();
    expect(screen.getByText('directDelegateOff')).toBeInTheDocument();
  });
});

describe('just-in-time team blueprints', () => {
  const research = ['web_researcher', 'data_analyst'];
  const audit = ['security_expert', 'perf_expert'];

  it('starts without a team and without the memory switch', () => {
    render(<AgentConfigPanel />);

    expect(screen.getByText('jitTeamOff')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('offers the two blueprints after the off entry', async () => {
    const user = userEvent.setup();
    render(<AgentConfigPanel />);

    expect(await optionsOf(user, 'jitTeamOff')).toEqual([
      'jitTeamOff',
      'blueprints.research_squad',
      'blueprints.code_audit_squad',
    ]);
  });

  it('forms the research squad that inherits the conversation memory by default', async () => {
    const user = userEvent.setup();
    render(<AgentConfigPanel />);

    await pick(user, 'jitTeamOff', 'blueprints.research_squad');

    const squad = sessionConfig()?.ephemeralSubagents as Record<string, { context_mode: string; tools: string[] }>;
    expect(Object.keys(squad)).toEqual(research);
    expect(Object.values(squad).map((member) => member.context_mode)).toEqual(['fork', 'fork']);
    expect(squad.web_researcher.tools).toContain('web_search_tool');
    expect(screen.getByText('blueprints.research_squad')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'jitInheritMemory' })).toBeChecked();
  });

  it('forms the code audit squad', async () => {
    const user = userEvent.setup();
    render(<AgentConfigPanel />);

    await pick(user, 'jitTeamOff', 'blueprints.code_audit_squad');

    expect(Object.keys(sessionConfig()?.ephemeralSubagents ?? {})).toEqual(audit);
  });

  it('isolates the members when the memory switch is turned off and shares it again when turned on', async () => {
    const user = userEvent.setup();
    render(<AgentConfigPanel />);
    await pick(user, 'jitTeamOff', 'blueprints.research_squad');
    const modes = () =>
      Object.values(sessionConfig()?.ephemeralSubagents as Record<string, { context_mode: string }>).map(
        (member) => member.context_mode,
      );

    await user.click(screen.getByRole('switch', { name: 'jitInheritMemory' }));
    expect(modes()).toEqual(['isolated', 'isolated']);

    await user.click(screen.getByRole('switch', { name: 'jitInheritMemory' }));
    expect(modes()).toEqual(['fork', 'fork']);
  });

  it('applies the remembered memory choice to the next blueprint and clears the team with the off entry', async () => {
    const user = userEvent.setup();
    render(<AgentConfigPanel />);
    await pick(user, 'jitTeamOff', 'blueprints.research_squad');
    await user.click(screen.getByRole('switch', { name: 'jitInheritMemory' }));

    await pick(user, 'blueprints.research_squad', 'blueprints.code_audit_squad');
    const squad = sessionConfig()?.ephemeralSubagents as Record<string, { context_mode: string }>;
    expect(Object.keys(squad)).toEqual(audit);
    expect(Object.values(squad).map((member) => member.context_mode)).toEqual(['isolated', 'isolated']);

    await pick(user, 'blueprints.code_audit_squad', 'jitTeamOff');
    expect(sessionConfig()?.ephemeralSubagents).toEqual({});
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('never edits the shared blueprints when the memory choice differs from their default', async () => {
    const user = userEvent.setup();
    render(<AgentConfigPanel />);
    await pick(user, 'jitTeamOff', 'blueprints.research_squad');
    await user.click(screen.getByRole('switch', { name: 'jitInheritMemory' }));

    await pick(user, 'blueprints.research_squad', 'blueprints.code_audit_squad');

    const blueprintModes = BLUEPRINT_TEMPLATES.flatMap((template) =>
      Object.values(template.subagents).map((member) => member.context_mode),
    );
    expect(blueprintModes).toEqual(['fork', 'fork', 'fork', 'fork']);
    const [, audit] = BLUEPRINT_TEMPLATES;
    const squad = sessionConfig()?.ephemeralSubagents as Record<string, { tools: string[] }>;
    expect(squad.security_expert).not.toBe(audit.subagents.security_expert);
    expect(squad.security_expert.tools).not.toBe(audit.subagents.security_expert.tools);
  });

  it.each([
    ['the research squad', { web_researcher: { context_mode: 'fork' } }, 'blueprints.research_squad'],
    ['the code audit squad', { security_expert: { context_mode: 'fork' } }, 'blueprints.code_audit_squad'],
  ])('recognises %s in the conversation configuration', (_label, ephemeralSubagents, shown) => {
    configureTeam(ephemeralSubagents);

    render(<AgentConfigPanel />);

    expect(screen.getByText(shown)).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('labels a team that matches no blueprint as a custom team and keeps the memory switch', () => {
    configureTeam({ custom_helper: { context_mode: 'fork' } });

    render(<AgentConfigPanel />);

    expect(screen.getByText('jitTeamCustom')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'jitInheritMemory' })).toBeChecked();
  });

  it('shows the memory choice the configured team really has', () => {
    configureTeam({
      web_researcher: { context_mode: 'isolated' },
      data_analyst: { context_mode: 'isolated' },
    });

    render(<AgentConfigPanel />);

    expect(screen.getByRole('switch', { name: 'jitInheritMemory' })).not.toBeChecked();
  });

  it('treats a member without a context mode as isolated, the way the agent runs it', () => {
    configureTeam({ custom_helper: {} });

    render(<AgentConfigPanel />);

    expect(screen.getByRole('switch', { name: 'jitInheritMemory' })).not.toBeChecked();
  });

  it.each([null, 'shared'])('treats the context mode %j as isolated: only fork inherits the memory', (mode) => {
    configureTeam({ custom_helper: { context_mode: mode } });

    render(<AgentConfigPanel />);

    expect(screen.getByRole('switch', { name: 'jitInheritMemory' })).not.toBeChecked();
  });

  it('treats a member that is not an object as isolated instead of failing', () => {
    configureTeam({ broken: null });

    render(<AgentConfigPanel />);

    expect(screen.getByRole('switch', { name: 'jitInheritMemory' })).not.toBeChecked();
  });

  it('keeps the memory choice when the panel is collapsed and opened again', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<AgentConfigPanel />);
    await pick(user, 'jitTeamOff', 'blueprints.research_squad');
    await user.click(screen.getByRole('switch', { name: 'jitInheritMemory' }));

    mocks.panel.isConfigPanelExpanded = false;
    refresh(rerender);
    expect(screen.queryByRole('switch')).toBeNull();
    mocks.panel.isConfigPanelExpanded = true;
    refresh(rerender);

    expect(screen.getByRole('switch', { name: 'jitInheritMemory' })).not.toBeChecked();
  });

  it('switches every member of a team whose members differ, to the same choice', async () => {
    configureTeam({ web_researcher: { context_mode: 'fork' }, data_analyst: { context_mode: 'isolated' } });
    const user = userEvent.setup();
    render(<AgentConfigPanel />);
    const memorySwitch = screen.getByRole('switch', { name: 'jitInheritMemory' });
    expect(memorySwitch).not.toBeChecked();

    await user.click(memorySwitch);

    const squad = sessionConfig()?.ephemeralSubagents as Record<string, { context_mode: string }>;
    expect(Object.values(squad).map((member) => member.context_mode)).toEqual(['fork', 'fork']);
    expect(screen.getByRole('switch', { name: 'jitInheritMemory' })).toBeChecked();
  });
});

describe('memory selectors', () => {
  it('start from the normal decay and the automatic extraction', () => {
    render(<AgentConfigPanel />);

    expect(screen.getByText('memoryDecayNormal')).toBeInTheDocument();
    expect(screen.getByText('memoryPresetAuto')).toBeInTheDocument();
  });

  it('list every decay speed and every extraction preset', async () => {
    const user = userEvent.setup();
    render(<AgentConfigPanel />);

    expect(await optionsOf(user, 'memoryDecayNormal')).toEqual([
      'memoryDecayPermanent',
      'memoryDecayNormal',
      'memoryDecayFast',
    ]);
    expect(await optionsOf(user, 'memoryPresetAuto')).toEqual([
      'memoryPresetAuto',
      'memoryPresetPersona',
      'memoryPresetWork',
      'memoryPresetResearch',
      'memoryPresetNone',
    ]);
  });

  it('write the chosen decay speed and extraction preset into the session configuration', async () => {
    const user = userEvent.setup();
    render(<AgentConfigPanel />);

    await pick(user, 'memoryDecayNormal', 'memoryDecayFast');
    await pick(user, 'memoryPresetAuto', 'memoryPresetWork');

    expect(sessionConfig()).toMatchObject({ memoryDecayProfile: 'fast', memoryExtractionPreset: 'work_assistant' });
    expect(screen.getByText('memoryDecayFast')).toBeInTheDocument();
    expect(screen.getByText('memoryPresetWork')).toBeInTheDocument();
  });

  it('show what the session configuration already says', () => {
    useChatStore.setState({
      agentConfig: {
        selectedSkillIds: [],
        selectedMcpNames: [],
        systemPrompt: '',
        useGlobalInstruction: true,
        memoryDecayProfile: 'permanent',
        memoryExtractionPreset: 'research',
      },
    });

    render(<AgentConfigPanel />);

    expect(screen.getByText('memoryDecayPermanent')).toBeInTheDocument();
    expect(screen.getByText('memoryPresetResearch')).toBeInTheDocument();
  });
});
