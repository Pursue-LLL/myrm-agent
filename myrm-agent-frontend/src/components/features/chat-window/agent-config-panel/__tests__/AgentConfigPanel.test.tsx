/**
 * The configuration panel under the message box, with the hook's state supplied by the test.
 *
 * Real scenario: the user opens "details and fine-tuning" from the agent chip, reads the four configuration cards,
 * adjusts them in the edit dialog and, when no saved agent backs the conversation, saves the combination as a new
 * agent. The advanced selectors have their own file (AgentConfigPanel.advanced.test.tsx).
 */
import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps, ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ActionMode, AgentConfig, BuiltinToolId } from '@/store/chat/types';
import { DEFAULT_ENABLED_BUILTIN_TOOLS } from '@/store/chat/types';
import type { MCPServiceConfig } from '@/store/config/types';
import type { Skill } from '@/store/skill/types';

import type AgentConfigCards from '../AgentConfigCards';
import type { ConfigCardType } from '../AgentConfigCards';
import type AgentConfigEditDialog from '../AgentConfigEditDialog';
import type TypewriterWelcome from '../TypewriterWelcome';

type CardsProps = ComponentProps<typeof AgentConfigCards>;
type DialogProps = ComponentProps<typeof AgentConfigEditDialog>;
type TypewriterProps = ComponentProps<typeof TypewriterWelcome>;

interface PanelState {
  isSavingAgent: boolean;
  editDialogOpen: boolean;
  editDialogType: ConfigCardType;
  showTypewriter: boolean;
  hasSavableConfig: boolean;
  agentConfig: AgentConfig | null;
  actionMode: ActionMode;
  isConfigPanelExpanded: boolean;
  enabledSkills: Skill[];
  enabledMcps: MCPServiceConfig[];
  selectedSkillDetails: Skill[];
  selectedMcpDetails: MCPServiceConfig[];
  currentBuiltinTools: BuiltinToolId[];
  setEditDialogOpen: (open: boolean) => void;
  handleCardClick: (type: ConfigCardType) => void;
  handleSaveConfig: (data: Partial<AgentConfig>) => void;
  handleSaveAsNewAgent: () => Promise<void>;
  handleTypewriterComplete: () => void;
  refreshSkills: () => Promise<void>;
  t: (key: string) => string;
  tIndicator: (key: string) => string;
}

const mocks = vi.hoisted(() => ({
  panel: undefined as PanelState | undefined,
  cardsProps: undefined as CardsProps | undefined,
  dialogProps: undefined as DialogProps | undefined,
  typewriterProps: undefined as TypewriterProps | undefined,
  setEditDialogOpen: vi.fn<(open: boolean) => void>(),
  handleCardClick: vi.fn<(type: ConfigCardType) => void>(),
  handleSaveConfig: vi.fn<(data: Partial<AgentConfig>) => void>(),
  handleSaveAsNewAgent: vi.fn<() => Promise<void>>(),
  handleTypewriterComplete: vi.fn<() => void>(),
  refreshSkills: vi.fn<() => Promise<void>>(),
  triggerPrewarm: vi.fn<() => Promise<void>>(),
}));

vi.mock('@/hooks/agent/useAgentConfigPanel', () => ({
  useAgentConfigPanel: () => {
    if (!mocks.panel) {
      throw new Error('The test did not supply the panel state');
    }
    return mocks.panel;
  },
}));
vi.mock('@/hooks/chat/useChatTurnPrewarm', () => ({
  useChatTurnPrewarm: () => ({ triggerPrewarm: mocks.triggerPrewarm }),
}));
vi.mock('@/services/config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/config')>()),
  getConfigSyncManager: () => ({ get: () => undefined }),
}));
vi.mock('../AgentConfigCards', () => ({
  default: (props: CardsProps) => {
    mocks.cardsProps = props;
    return <button type="button" data-testid="cards" aria-label="cards" onClick={() => props.onCardClick('mcp')} />;
  },
}));
vi.mock('../TypewriterWelcome', () => ({
  default: (props: TypewriterProps) => {
    mocks.typewriterProps = props;
    return (
      <button type="button" data-testid="typewriter" onClick={() => props.onComplete?.()}>
        {props.text}
      </button>
    );
  },
}));
vi.mock('../AgentConfigEditDialog', () => ({
  default: (props: DialogProps) => {
    mocks.dialogProps = props;
    return <div data-testid="edit-dialog" />;
  },
}));

import AgentConfigPanel from '../AgentConfigPanel';

const identity = (key: string) => key;

function panelState(overrides: Partial<PanelState> = {}): PanelState {
  return {
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
    currentBuiltinTools: [...DEFAULT_ENABLED_BUILTIN_TOOLS],
    setEditDialogOpen: mocks.setEditDialogOpen,
    handleCardClick: mocks.handleCardClick,
    handleSaveConfig: mocks.handleSaveConfig,
    handleSaveAsNewAgent: mocks.handleSaveAsNewAgent,
    handleTypewriterComplete: mocks.handleTypewriterComplete,
    refreshSkills: mocks.refreshSkills,
    t: identity,
    tIndicator: identity,
    ...overrides,
  };
}

function config(overrides: Partial<AgentConfig> = {}): AgentConfig {
  return { selectedSkillIds: [], selectedMcpNames: [], systemPrompt: '', useGlobalInstruction: true, ...overrides };
}

function show(overrides: Partial<PanelState> = {}) {
  mocks.panel = panelState(overrides);
  return render(<AgentConfigPanel />);
}

// The panel is memoized: a re-render needs a changed prop to read the hook state again.
let rerenderCount = 0;
function refresh(rerender: (ui: ReactElement) => void, state: Partial<PanelState> = {}) {
  mocks.panel = panelState(state);
  rerenderCount += 1;
  rerender(<AgentConfigPanel className={`render-${rerenderCount}`} />);
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.panel = undefined;
  mocks.cardsProps = undefined;
  mocks.dialogProps = undefined;
  mocks.typewriterProps = undefined;
  mocks.triggerPrewarm.mockResolvedValue(undefined);
});

describe('AgentConfigPanel: shell', () => {
  it('renders nothing outside agent mode', () => {
    const { container } = show({ actionMode: 'fast', isConfigPanelExpanded: true });

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('edit-dialog')).toBeNull();
  });

  it('keeps the body hidden while collapsed and still mounts the edit dialog', async () => {
    show({ isConfigPanelExpanded: false });

    expect(screen.queryByTestId('cards')).toBeNull();
    expect(screen.queryByTestId('typewriter')).toBeNull();
    expect(screen.queryByText('memoryDecay')).toBeNull();
    expect(await screen.findByTestId('edit-dialog')).toBeInTheDocument();
  });

  it('shows the welcome message, the cards and the advanced settings when expanded', () => {
    const selectedSkillDetails: Skill[] = [];
    const selectedMcpDetails: MCPServiceConfig[] = [];
    const currentBuiltinTools: BuiltinToolId[] = ['web_search'];
    show({
      showTypewriter: true,
      selectedSkillDetails,
      selectedMcpDetails,
      currentBuiltinTools,
      agentConfig: config({
        systemPrompt: 'Be brief',
        useGlobalInstruction: false,
        ephemeralSubagents: { writer: {} },
      }),
    });

    expect(screen.getByTestId('typewriter')).toHaveTextContent('welcomeMessage');
    expect(mocks.typewriterProps).toMatchObject({ show: true, typingSpeed: 35, displayDuration: 1200 });
    expect(mocks.cardsProps).toMatchObject({
      selectedSkills: selectedSkillDetails,
      selectedMcps: selectedMcpDetails,
      systemPrompt: 'Be brief',
      useGlobalInstruction: false,
      enabledBuiltinTools: currentBuiltinTools,
      ephemeralSubagents: { writer: {} },
    });
    expect(screen.getByText('jitTeam')).toBeInTheDocument();
    expect(screen.getByText('memoryDecay')).toBeInTheDocument();
    expect(screen.getByText('memoryExtractionPreset')).toBeInTheDocument();
  });

  it('hands the cards defaults while no configuration exists', () => {
    show({ agentConfig: null });

    expect(mocks.cardsProps).toMatchObject({ systemPrompt: '', useGlobalInstruction: true });
    expect(mocks.cardsProps?.ephemeralSubagents).toBeUndefined();
  });

  it('forwards card clicks and the end of the welcome message to the hook', () => {
    show({ showTypewriter: true });

    fireEvent.click(screen.getByTestId('cards'));
    expect(mocks.handleCardClick).toHaveBeenCalledWith('mcp');

    fireEvent.click(screen.getByTestId('typewriter'));
    expect(mocks.handleTypewriterComplete).toHaveBeenCalledTimes(1);
  });

  it('puts the class name on the expanded body only', () => {
    mocks.panel = panelState();
    const { container, unmount } = render(<AgentConfigPanel className="custom-body" />);
    expect(container.querySelector('.custom-body')).toHaveClass('animate-in');
    unmount();

    mocks.panel = panelState({ isConfigPanelExpanded: false });
    const collapsed = render(<AgentConfigPanel className="custom-body" />);
    expect(collapsed.container.querySelector('.custom-body')).toBeNull();
  });
});

describe('AgentConfigPanel: edit dialog', () => {
  it('receives the configuration of the conversation and the hook actions', async () => {
    const enabledSkills: Skill[] = [];
    const enabledMcps: MCPServiceConfig[] = [];
    show({
      editDialogOpen: true,
      editDialogType: 'instruction',
      enabledSkills,
      enabledMcps,
      currentBuiltinTools: ['browser'],
      agentConfig: config({
        selectedSkillIds: ['s1'],
        skillConfigs: { s1: { is_core: true, instance_name: null } },
        selectedMcpNames: ['m1'],
        mcpToolSelections: { m1: ['search'] },
        systemPrompt: 'Be brief',
        useGlobalInstruction: false,
        browserSource: 'extension',
        dialogPolicy: 'auto_dismiss',
        autoRestoreDomains: ['example.com'],
        ephemeralSubagents: { writer: {} },
      }),
    });
    await screen.findByTestId('edit-dialog');

    expect(mocks.dialogProps).toMatchObject({
      open: true,
      type: 'instruction',
      enabledSkills,
      enabledMcps,
      selectedSkillIds: ['s1'],
      skillConfigs: { s1: { is_core: true, instance_name: null } },
      selectedMcpNames: ['m1'],
      mcpToolSelections: { m1: ['search'] },
      systemPrompt: 'Be brief',
      useGlobalInstruction: false,
      enabledBuiltinTools: ['browser'],
      browserSource: 'extension',
      dialogPolicy: 'auto_dismiss',
      autoRestoreDomains: ['example.com'],
      ephemeralSubagents: { writer: {} },
      onOpenChange: mocks.setEditDialogOpen,
      onSave: mocks.handleSaveConfig,
      onRefreshSkills: mocks.refreshSkills,
    });
  });

  it('receives empty defaults without a configuration, with one shared list for the restore domains', async () => {
    const { rerender } = show({ agentConfig: null });
    await screen.findByTestId('edit-dialog');
    const firstDomains = mocks.dialogProps?.autoRestoreDomains;

    expect(mocks.dialogProps).toMatchObject({
      selectedSkillIds: [],
      skillConfigs: {},
      selectedMcpNames: [],
      systemPrompt: '',
      useGlobalInstruction: true,
      ephemeralSubagents: {},
      autoRestoreDomains: [],
    });

    mocks.dialogProps = undefined;
    refresh(rerender, { agentConfig: null });
    const latestDialogProps = (): DialogProps | undefined => mocks.dialogProps;
    expect(latestDialogProps()?.autoRestoreDomains).toBe(firstDomains);
  });
});

describe('AgentConfigPanel: turn prewarm', () => {
  it('warms the turn for the conversation agent and again when the agent changes', () => {
    const { rerender } = show({ agentConfig: config({ agentId: 'agent-1' }) });
    expect(mocks.triggerPrewarm).toHaveBeenCalledTimes(1);

    refresh(rerender, { agentConfig: config({ agentId: 'agent-1' }) });
    expect(mocks.triggerPrewarm).toHaveBeenCalledTimes(1);

    refresh(rerender, { agentConfig: config({ agentId: 'agent-2' }) });
    expect(mocks.triggerPrewarm).toHaveBeenCalledTimes(2);
  });

  it.each([
    ['without a saved agent', { agentConfig: config() }],
    ['outside agent mode', { actionMode: 'fast' as const, agentConfig: config({ agentId: 'agent-1' }) }],
  ])('does not warm the turn %s', (_label, overrides) => {
    show(overrides);

    expect(mocks.triggerPrewarm).not.toHaveBeenCalled();
  });
});

describe('AgentConfigPanel: saving', () => {
  it('offers nothing to save while the hook finds nothing worth saving', () => {
    show({ hasSavableConfig: false, agentConfig: config({ autoRestoreDomains: ['example.com'] }) });

    expect(screen.queryByRole('button', { name: /saveAsNewAgent/ })).toBeNull();
    expect(screen.queryByText('saveAsNewAgentTip')).toBeNull();
  });

  it('offers to save a configuration without a saved agent as a new agent', () => {
    show({ hasSavableConfig: true, agentConfig: config({ selectedSkillIds: ['s1'] }) });

    expect(screen.getByText('saveAsNewAgentTip')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'saveAsNewAgent' }));
    expect(mocks.handleSaveAsNewAgent).toHaveBeenCalledTimes(1);
  });

  it('also offers it before any configuration exists once the hook finds something to save', () => {
    show({ hasSavableConfig: true, agentConfig: null });

    expect(screen.getByRole('button', { name: 'saveAsNewAgent' })).toBeInTheDocument();
  });

  it('shows the saving state and blocks the button while the agent is created', () => {
    show({ hasSavableConfig: true, isSavingAgent: true, agentConfig: config({ systemPrompt: 'Be brief' }) });

    const button = screen.getByRole('button', { name: 'savingAgent' });
    expect(button).toBeDisabled();
  });

  it('offers no save button for a conversation backed by a saved agent, whatever was changed', () => {
    show({ hasSavableConfig: true, agentConfig: config({ agentId: 'agent-1', selectedSkillIds: ['s1'] }) });

    expect(screen.queryByRole('button', { name: /sav/i })).toBeNull();
    expect(screen.queryByText('saveAsNewAgentTip')).toBeNull();
  });
});
