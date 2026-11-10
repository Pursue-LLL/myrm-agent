/**
 * The edit dialog behind the configuration cards.
 *
 * Real scenario: the user clicks one card of the configuration panel, adjusts that card's settings in the dialog and
 * confirms; the dialog hands exactly that card's settings to the panel. What the dialog starts from and keeps while
 * it is open is in AgentConfigEditDialog.draft.test.tsx; prompt generation, history and the action space estimate are
 * in AgentConfigEditDialog.assist.test.tsx.
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ConfigCardType } from '../AgentConfigCards';
import {
  builtin,
  confirm,
  dialogProps,
  instructionPanel,
  kit,
  mcp,
  resetKit,
  settingsSheet,
  skillsPanel,
  subagentsPanel,
  type DialogProps,
} from './editDialogKit';

vi.mock('next/dynamic', async () => (await import('./editDialogKit')).nextDynamicMock());
vi.mock('@/hooks/billing/useFeatureEntitlements', async () => (await import('./editDialogKit')).entitlementsMock());
vi.mock('@/lib/deploy-mode', async (importOriginal) =>
  (await import('./editDialogKit')).deployModeMock(await importOriginal<typeof import('@/lib/deploy-mode')>()),
);
vi.mock('../ActionSpaceAccuracyRadar', async () => (await import('./editDialogKit')).radarMock());
vi.mock('../SkillsSectionPanel', async () => (await import('./editDialogKit')).skillsPanelMock());
vi.mock('../BuiltinToolsPanel', async () => (await import('./editDialogKit')).builtinToolsPanelMock());
vi.mock('../SubagentsPanel', async () => (await import('./editDialogKit')).subagentsPanelMock());
vi.mock('../InstructionPanel', async () => (await import('./editDialogKit')).instructionPanelMock());

import AgentConfigEditDialog from '../AgentConfigEditDialog';

function show(type: ConfigCardType, overrides: Partial<DialogProps> = {}) {
  return render(<AgentConfigEditDialog {...dialogProps(type, overrides)} />);
}

beforeEach(() => {
  vi.resetAllMocks();
  resetKit();
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ data: null }), { status: 200 })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AgentConfigEditDialog: saving', () => {
  it('hands over the chosen skills with their configuration and closes', () => {
    show('skills');

    act(() => {
      skillsPanel().setLocalSkillIds(['s1', 's2']);
      skillsPanel().setLocalSkillConfigs({ s2: { is_core: true } });
    });
    fireEvent.click(confirm());

    expect(kit.onSave).toHaveBeenCalledExactlyOnceWith({
      selectedSkillIds: ['s1', 's2'],
      skillConfigs: { s2: { is_core: true } },
    });
    expect(kit.onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
  });

  it('hands over the MCP servers with the tool choice of each server', () => {
    show('mcp');

    fireEvent.click(screen.getByTestId('mcp-web'));
    fireEvent.click(screen.getByRole('button', { name: 'choose-docs' }));
    fireEvent.click(screen.getByRole('button', { name: 'choose-web' }));
    fireEvent.click(confirm());

    expect(kit.onSave).toHaveBeenCalledExactlyOnceWith({
      selectedMcpNames: ['docs', 'web'],
      mcpToolSelections: { docs: ['search'], web: ['search'] },
    });
  });

  it('hands over no tool choice when none is left, and takes a server out again', () => {
    show('mcp', { mcpToolSelections: { docs: ['read'] } });

    fireEvent.click(screen.getByRole('button', { name: 'reset-docs' }));
    fireEvent.click(screen.getByTestId('mcp-docs'));
    fireEvent.click(confirm());

    expect(kit.onSave).toHaveBeenCalledExactlyOnceWith({ selectedMcpNames: [], mcpToolSelections: undefined });
  });

  it('hands over the instruction and whether the global instruction still applies', () => {
    show('instruction');

    fireEvent.click(screen.getByRole('button', { name: 'type-prompt' }));
    fireEvent.click(screen.getByRole('button', { name: 'drop-global' }));
    fireEvent.click(confirm());

    expect(kit.onSave).toHaveBeenCalledExactlyOnceWith({
      systemPrompt: 'Answer in French',
      useGlobalInstruction: false,
    });
  });

  it('hands over the built-in tools with the browser, dialog and recording choices', () => {
    show('builtin_tools', {
      autoRestoreDomains: ['example.com'],
      browserSource: 'launch',
      dialogPolicy: 'smart',
      sessionRecording: 'off',
    });

    act(() => {
      builtin().setLocalBuiltinTools(['web_search', 'memory']);
      builtin().setLocalAutoRestoreDomains(['example.com', 'docs.dev']);
      builtin().setLocalBrowserSource('connect');
      builtin().setLocalDialogPolicy('auto_dismiss');
      builtin().setLocalSessionRecording('always');
    });
    fireEvent.click(confirm());

    expect(kit.onSave).toHaveBeenCalledExactlyOnceWith({
      enabledBuiltinTools: ['web_search', 'memory'],
      autoRestoreDomains: ['example.com', 'docs.dev'],
      browserSource: 'connect',
      dialogPolicy: 'auto_dismiss',
      sessionRecording: 'always',
    });
  });

  it('hands over the subagent team', () => {
    show('subagents', { ephemeralSubagents: { writer: { display_name: 'Writer' } } });

    act(() => subagentsPanel().setLocalEphemeralSubagents({ writer: { display_name: 'Writer' }, critic: {} }));
    fireEvent.click(confirm());

    expect(kit.onSave).toHaveBeenCalledExactlyOnceWith({
      ephemeralSubagents: { writer: { display_name: 'Writer' }, critic: {} },
    });
  });

  it('keeps a team with an invalid display name from being saved and stays open', () => {
    show('subagents');

    act(() => subagentsPanel().setDisplayNameErrors({ writer: 'duplicate' }));
    fireEvent.click(confirm());

    expect(kit.onSave).not.toHaveBeenCalled();
    expect(kit.onOpenChange).not.toHaveBeenCalled();
  });

  it('does not let a cleared name error keep the team from being saved', () => {
    show('subagents');

    act(() => subagentsPanel().setDisplayNameErrors({ writer: '' }));
    fireEvent.click(confirm());

    expect(kit.onSave).toHaveBeenCalledOnce();
  });

  it('closes without saving when dismissed with Escape', () => {
    show('skills');

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(kit.onSave).not.toHaveBeenCalled();
    expect(kit.onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
  });

  it('closes without saving on cancel', () => {
    show('skills');

    fireEvent.click(screen.getByRole('button', { name: 'cancel' }));

    expect(kit.onSave).not.toHaveBeenCalled();
    expect(kit.onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
  });
});

describe('AgentConfigEditDialog: what it shows', () => {
  it.each<[ConfigCardType, string, boolean]>([
    ['skills', 'skillsSection', true],
    ['mcp', 'mcpSection', true],
    ['builtin_tools', 'builtinToolsSection', true],
    ['subagents', 'subagentsSection', true],
    ['instruction', 'instructionSection', false],
  ])('titles the %s card and shows the action space estimate only where it matters', (type, title, hasEstimate) => {
    show(type);

    expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
    expect(screen.queryByTestId('radar') !== null).toBe(hasEstimate);
  });

  it('describes every card except the instruction', () => {
    const { unmount } = show('skills');
    expect(screen.getByText('skillsSectionDesc')).toBeInTheDocument();
    unmount();

    show('instruction');
    expect(screen.queryByText(/SectionDesc$/)).toBeNull();
  });

  it('lists the first-screen catalog of the skills only on the skills card', () => {
    const { unmount } = show('skills');
    expect(screen.getByTestId('radar')).toHaveAttribute('data-turn1-catalog', 'true');
    unmount();

    show('mcp');
    expect(screen.getByTestId('radar')).toHaveAttribute('data-turn1-catalog', 'false');
  });

  it('filters the MCP servers by the search text and tells each tool choice whether its server is on', () => {
    show('mcp');
    expect(screen.queryByText('noEnabledMcp')).toBeNull();

    expect(screen.getByTestId('tools-docs')).toHaveAttribute('data-server-enabled', 'true');
    expect(screen.getByTestId('tools-web')).toHaveAttribute('data-server-enabled', 'false');

    fireEvent.change(screen.getByPlaceholderText('searchPlaceholder'), { target: { value: 'WEB' } });

    expect(screen.queryByTestId('mcp-docs')).toBeNull();
    expect(screen.getByTestId('mcp-web')).toBeInTheDocument();
  });

  it('shows the tools already chosen for each server', () => {
    show('mcp', { mcpToolSelections: { docs: ['search'] } });

    expect(screen.getByTestId('tools-docs')).toHaveAttribute('data-selected', '["search"]');
    expect(screen.getByTestId('tools-web')).toHaveAttribute('data-selected', 'null');
  });

  it('describes each MCP server, or names its type when it has no description', () => {
    show('mcp', { enabledMcps: [mcp('docs'), { ...mcp('plain'), description: '' }] });

    expect(screen.getByText('docs server')).toBeInTheDocument();
    expect(screen.getByText('sse')).toBeInTheDocument();
  });

  it('says so when no MCP server is enabled and still offers adding one', () => {
    show('mcp', { enabledMcps: [] });

    expect(screen.getByText('noEnabledMcp')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('searchPlaceholder')).toBeNull();
    expect(screen.getByRole('button', { name: /addMore/ })).toBeInTheDocument();
  });

  it('lets the instruction panel reveal a hidden system prompt', () => {
    const reveal = vi.fn();
    show('instruction', { isSystemPromptHidden: true, loadingSystemPrompt: true, onShowSystemPrompt: reveal });

    expect(instructionPanel()).toMatchObject({
      isSystemPromptHidden: true,
      loadingSystemPrompt: true,
      onShowSystemPrompt: reveal,
    });
  });

  it('shows the system prompt unless told it is hidden', () => {
    show('instruction');

    expect(instructionPanel()).toMatchObject({ isSystemPromptHidden: false, loadingSystemPrompt: false });
  });

  it('passes the agent to the skills panel', () => {
    show('skills', { agentId: 'agent-7' });

    expect(screen.getByTestId('skills-panel')).toHaveAttribute('data-agent', 'agent-7');
  });
});

describe('AgentConfigEditDialog: settings sheet', () => {
  it('opens the skill settings from the skills card and closes them with the one close button', () => {
    show('skills');
    expect(screen.queryByTestId('skills-settings')).toBeNull();

    act(() => skillsPanel().onOpenSettingsSheet('skills'));
    const sheet = settingsSheet('skills-settings');
    expect(screen.queryByTestId('mcp-settings')).toBeNull();
    expect(within(sheet).getByText('skillsSection')).toBeInTheDocument();

    const closeButtons = within(sheet).getAllByRole('button');
    expect(closeButtons).toHaveLength(1);
    fireEvent.click(closeButtons[0]);

    expect(screen.queryByTestId('agent-config-settings-sheet')).toBeNull();
  });

  it('closes the settings with Escape while the dialog stays open', () => {
    show('skills');
    act(() => skillsPanel().onOpenSettingsSheet('skills'));

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByTestId('skills-settings')).toBeNull();
    expect(kit.onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByTestId('skills-panel')).toBeInTheDocument();
  });

  it('opens the MCP settings from the add button of the MCP card', () => {
    show('mcp');

    fireEvent.click(screen.getByRole('button', { name: /addMore/ }));

    expect(screen.getByTestId('mcp-settings')).toBeInTheDocument();
    expect(within(settingsSheet('mcp-settings')).getByText('mcpSection')).toBeInTheDocument();
    expect(screen.queryByTestId('skills-settings')).toBeNull();
  });
});
