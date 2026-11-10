/**
 * What the edit dialog starts from, keeps and gates.
 *
 * Real scenario: the dialog stays mounted for the whole life of the panel while the panel's settings change under it
 * (another agent is summoned, a background load finishes). Every time it opens it must show the settings of that
 * moment, while it is open it must keep what the user typed even though the panel renders it again with fresh
 * objects, and once it closes unsaved changes are gone. It also refuses to confirm an external CLI that cannot run
 * and leaves out the tools the plan does not include.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { BuiltinToolId } from '@/store/chat/types';

import type { ConfigCardType } from '../AgentConfigCards';
import { builtin, confirm, dialogProps, kit, resetKit, type DialogProps } from './editDialogKit';

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
  const view = render(<AgentConfigEditDialog {...dialogProps(type, overrides)} />);
  // The panel hands the dialog fresh arrays and objects on every render, so an update changes every identity.
  const update = (next: Partial<DialogProps>) =>
    view.rerender(<AgentConfigEditDialog {...dialogProps(type, { ...overrides, ...next })} />);
  return { ...view, update };
}

const builtinPanel = () => screen.getByTestId('builtin-panel');
const instructionPanel = () => screen.getByTestId('instruction-panel');

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

describe('AgentConfigEditDialog: the settings it edits', () => {
  it('starts from the settings it is given', () => {
    show('builtin_tools', {
      enabledBuiltinTools: ['memory'],
      autoRestoreDomains: ['a.com'],
      browserSource: 'extension',
      dialogPolicy: 'wait_for_agent',
      sessionRecording: 'on_failure',
    });

    expect(builtinPanel()).toHaveAttribute('data-tools', 'memory');
    expect(builtinPanel()).toHaveAttribute('data-domains', 'a.com');
    expect(builtinPanel()).toHaveAttribute('data-source', 'extension');
    expect(builtinPanel()).toHaveAttribute('data-policy', 'wait_for_agent');
    expect(builtinPanel()).toHaveAttribute('data-recording', 'on_failure');
  });

  it('starts from the instruction switch and the team it is given', () => {
    const team = { writer: { display_name: 'Writer' } };
    const instruction = show('instruction', { useGlobalInstruction: false });
    expect(instructionPanel()).toHaveAttribute('data-global', 'false');
    instruction.unmount();

    show('subagents', { ephemeralSubagents: team });
    expect(screen.getByTestId('subagents-panel')).toHaveAttribute('data-team', JSON.stringify(team));
  });

  it('starts empty when the conversation has no settings yet, with the global instruction on', () => {
    const instruction = show('instruction', { systemPrompt: undefined, useGlobalInstruction: undefined });
    expect(instructionPanel()).toHaveAttribute('data-prompt', '');
    expect(instructionPanel()).toHaveAttribute('data-global', 'true');
    instruction.unmount();

    const skills = show('skills', { selectedSkillIds: undefined, skillConfigs: undefined });
    expect(screen.getByTestId('skills-panel')).toHaveAttribute('data-ids', '');
    expect(screen.getByTestId('skills-panel')).toHaveAttribute('data-configs', '{}');
    skills.unmount();

    show('builtin_tools', { autoRestoreDomains: undefined, browserSource: undefined });
    expect(builtinPanel()).toHaveAttribute('data-domains', '');
    expect(builtinPanel()).toHaveAttribute('data-source', '');
    expect(builtinPanel()).toHaveAttribute('data-policy', '');
    expect(builtinPanel()).toHaveAttribute('data-recording', '');
  });

  it('starts the MCP and subagent cards empty when there are no settings yet', () => {
    const mcpCard = show('mcp', { selectedMcpNames: undefined, mcpToolSelections: undefined });
    expect(screen.getByTestId('tools-docs')).toHaveAttribute('data-server-enabled', 'false');
    fireEvent.click(confirm());
    expect(kit.onSave).toHaveBeenLastCalledWith({ selectedMcpNames: [], mcpToolSelections: undefined });
    mcpCard.unmount();

    show('subagents', { ephemeralSubagents: undefined });
    expect(screen.getByTestId('subagents-panel')).toHaveAttribute('data-team', '{}');
  });

  it('shows the browser, dialog and recording settings of the moment it is opened, not of an earlier agent', () => {
    const view = show('builtin_tools', {
      open: false,
      browserSource: 'launch',
      dialogPolicy: 'smart',
      sessionRecording: 'off',
      autoRestoreDomains: ['old.com'],
      enabledBuiltinTools: ['web_search'],
    });

    view.update({
      open: true,
      browserSource: 'connect',
      dialogPolicy: 'auto_accept',
      sessionRecording: 'always',
      autoRestoreDomains: ['new.com'],
      enabledBuiltinTools: ['memory'],
    });

    expect(builtinPanel()).toHaveAttribute('data-source', 'connect');
    expect(builtinPanel()).toHaveAttribute('data-policy', 'auto_accept');
    expect(builtinPanel()).toHaveAttribute('data-recording', 'always');
    expect(builtinPanel()).toHaveAttribute('data-domains', 'new.com');
    expect(builtinPanel()).toHaveAttribute('data-tools', 'memory');
  });

  it('shows the MCP tool choice of the moment it is opened, not of an earlier agent', () => {
    const view = show('mcp', { open: false, mcpToolSelections: { docs: ['read'] } });

    view.update({ open: true, mcpToolSelections: { web: ['fetch'] } });
    fireEvent.click(confirm());

    expect(screen.queryByTestId('tools-docs')).toHaveAttribute('data-selected', 'null');
    expect(kit.onSave).toHaveBeenCalledExactlyOnceWith({
      selectedMcpNames: ['docs'],
      mcpToolSelections: { web: ['fetch'] },
    });
  });

  it('keeps what the user typed when the panel renders again with the same settings', () => {
    const view = show('instruction');
    fireEvent.click(screen.getByRole('button', { name: 'type-prompt' }));

    view.update({});

    expect(instructionPanel()).toHaveAttribute('data-prompt', 'Answer in French');
  });

  it('forgets unsaved changes when it is closed and opened again', () => {
    const view = show('instruction');
    fireEvent.click(screen.getByRole('button', { name: 'type-prompt' }));

    view.update({ open: false });
    view.update({ open: true });

    expect(instructionPanel()).toHaveAttribute('data-prompt', 'Be brief');
  });
});

describe('AgentConfigEditDialog: built-in tool gates', () => {
  it('keeps an external CLI without a ready backend from being confirmed in local mode', () => {
    kit.local = true;
    show('builtin_tools');
    expect(confirm()).toBeEnabled();

    act(() => builtin().setLocalBuiltinTools(['web_search', 'external_cli']));
    expect(confirm()).toBeDisabled();

    act(() => builtin().onExternalCliBackendReady?.(false));
    expect(confirm()).toBeDisabled();

    act(() => builtin().onExternalCliBackendReady?.(true));
    expect(confirm()).toBeEnabled();
  });

  it('does not block outside local mode or on any other card', () => {
    kit.local = false;
    const outsideLocal = show('builtin_tools', { enabledBuiltinTools: ['external_cli'] });
    expect(confirm()).toBeEnabled();
    outsideLocal.unmount();

    kit.local = true;
    show('skills', { enabledBuiltinTools: ['external_cli'] });
    expect(confirm()).toBeEnabled();
  });

  it('takes the tools the plan does not include out of the draft once the entitlements are known (sandbox)', () => {
    kit.sandbox = true;
    kit.entitlements = { canUseCron: false, canUseVnc: false, isLoading: true };
    const tools: BuiltinToolId[] = ['web_search', 'cron', 'computer_use', 'external_cli'];
    const view = show('builtin_tools', { enabledBuiltinTools: tools });
    expect(builtinPanel()).toHaveAttribute('data-tools', tools.join(','));

    kit.entitlements = { canUseCron: false, canUseVnc: true, isLoading: false };
    view.update({});

    expect(builtinPanel()).toHaveAttribute('data-tools', 'web_search,computer_use');
    fireEvent.click(confirm());
    expect(kit.onSave).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ enabledBuiltinTools: ['web_search', 'computer_use'] }),
    );
  });

  it('leaves the tools alone outside the sandbox', () => {
    kit.entitlements = { canUseCron: false, canUseVnc: false, isLoading: false };
    show('builtin_tools', { enabledBuiltinTools: ['cron', 'external_cli'] });

    expect(builtinPanel()).toHaveAttribute('data-tools', 'cron,external_cli');
  });
});
