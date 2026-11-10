/**
 * Test kit for FlowPadModal: stubs the chat and agent stores, the template and metrics services and the Tauri
 * bridge, so a test drives the real modal through its UI and observes every outgoing call.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { useFlowPadStore, type FlowPadCapture } from '@/store/useFlowPadStore';

type StoreListener = (state: Record<string, unknown>, prev: Record<string, unknown>) => void;

interface AgentListItem {
  id: string;
  name: string;
  avatar_url: string;
}

interface AgentDetail {
  id: string;
  user_id: string;
  name: string;
  system_prompt: string;
  skill_ids: string[];
  mcp_ids: string[];
  created_at: string;
  updated_at: string;
}

const hoisted = vi.hoisted(() => ({
  subscribers: [] as StoreListener[],
  chatState: {
    agentConfig: null as { agentId?: string; agentName?: string; name?: string; avatarUrl?: string } | null,
    sendMessage: vi.fn(),
    setFiles: vi.fn(),
    getCurrentSessionMessageId: vi.fn(),
    files: [] as unknown[],
    messages: [] as Array<{ role: string; content: string; messageId?: string }>,
    loading: false,
  },
  agentState: {
    agents: [] as AgentListItem[],
    loading: false,
    fetchAgents: vi.fn(),
    fetchAgent: vi.fn(),
  },
  mocks: {
    getTemplates: vi.fn(),
    instantiateTemplate: vi.fn(),
    invoke: vi.fn(),
    hideWindow: vi.fn(),
    isTauriRuntime: vi.fn(),
    toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
    metrics: {
      surfaceViewed: vi.fn(),
      searchUsed: vi.fn(),
      routeApplied: vi.fn(),
      routeApplyFailed: vi.fn(),
      firstMessageSent: vi.fn(),
    },
  },
}));

export const chatState = hoisted.chatState;
export const agentState = hoisted.agentState;
export const mocks = hoisted.mocks;

vi.mock('@/store/useChatStore', () => {
  const hook = vi.fn(() => hoisted.chatState);
  Object.assign(hook, {
    getState: () => hoisted.chatState,
    subscribe: (listener: StoreListener) => {
      hoisted.subscribers.push(listener);
      return () => {
        hoisted.subscribers = hoisted.subscribers.filter((candidate) => candidate !== listener);
      };
    },
    setState: vi.fn(),
  });
  return { default: hook };
});
vi.mock('@/store/useAgentStore', () => {
  const hook = <T,>(select: (state: typeof hoisted.agentState) => T): T => select(hoisted.agentState);
  Object.assign(hook, { getState: () => hoisted.agentState, setState: vi.fn(), subscribe: vi.fn() });
  return { default: hook };
});
vi.mock('@/lib/utils/toast', () => ({ toast: hoisted.mocks.toast }));
vi.mock('@/lib/utils/classnameUtils', () => ({ cn: (...args: string[]) => args.filter(Boolean).join(' ') }));
vi.mock('@radix-ui/react-visually-hidden', () => ({
  VisuallyHidden: ({ children }: { children: React.ReactNode }) => <span style={{ display: 'none' }}>{children}</span>,
}));
vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isTauriRuntime: () => hoisted.mocks.isTauriRuntime(),
}));
vi.mock('@/services/agentTemplates', () => ({ getTemplates: () => hoisted.mocks.getTemplates() }));
vi.mock('@/services/templateSummon', () => ({
  instantiateTemplateWithMetrics: (options: unknown) => hoisted.mocks.instantiateTemplate(options),
  extractSummonErrorMessage: (error: unknown, fallback: string) =>
    error instanceof Error && error.message.trim() ? error.message.trim() : fallback,
}));
vi.mock('@/services/expertSummonMetrics', () => ({
  recordExpertSummonSurfaceViewed: hoisted.mocks.metrics.surfaceViewed,
  recordExpertSummonSearchUsed: hoisted.mocks.metrics.searchUsed,
  recordExpertSummonRouteApplied: hoisted.mocks.metrics.routeApplied,
  recordExpertSummonRouteApplyFailed: hoisted.mocks.metrics.routeApplyFailed,
  recordExpertSummonFirstMessageSent: hoisted.mocks.metrics.firstMessageSent,
}));
vi.mock('@tauri-apps/api/core', () => ({ invoke: (...args: unknown[]) => hoisted.mocks.invoke(...args) }));
vi.mock('@tauri-apps/api/window', () => ({ getCurrentWindow: () => ({ hide: hoisted.mocks.hideWindow }) }));

import { FlowPadModal } from '../flow-pad-modal';

export const TEAM_TEMPLATE = {
  id: 'cloudq-team-template',
  name: 'CloudQ Team',
  description: 'Cloud incident experts',
  avatar_url: '',
  agent_type: 'team',
  members: [{ role: 'lead', name: 'CloudQ', description: 'Incident commander' }],
  use_cases: ['Diagnose cloud outage', 'Review migration risks'],
};

const SOLO_TEMPLATE = { ...TEAM_TEMPLATE, id: 'solo-template', name: 'Solo Helper', agent_type: 'individual' };

export function agentDetail(agentId: string): AgentDetail {
  // Profile names differ from the roster names on purpose: the route label must come from the roster entry.
  const names: Record<string, string> = {
    'writer-agent': 'Writer Profile',
    'cloudq-instance': 'CloudQ Team',
    'builtin-general': 'General Profile',
  };
  return {
    id: agentId,
    user_id: 'user-1',
    name: names[agentId] ?? agentId,
    system_prompt: agentId === 'writer-agent' ? 'Write with concise style.' : '',
    skill_ids: agentId === 'writer-agent' ? ['writing'] : [],
    mcp_ids: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

const BASE_ROSTER: AgentListItem[] = [
  { id: 'builtin-general', name: 'General Agent', avatar_url: '' },
  { id: 'writer-agent', name: 'Writer Agent', avatar_url: 'https://img.example/writer.png' },
];
const SUMMONED_AGENT: AgentListItem = { id: 'cloudq-instance', name: 'CloudQ Team', avatar_url: '' };

/** What the backend would list: a refresh copies it into the store, a summon grows it. */
let serverRoster: AgentListItem[] = BASE_ROSTER;

/** Clears every recorded call and restores the defaults the tests rely on. */
export function resetFlowPadKit(): void {
  vi.clearAllMocks();
  useFlowPadStore.getState().close();
  hoisted.subscribers = [];
  let nextRequestId = 0;
  chatState.agentConfig = { agentName: 'TestAgent' };
  chatState.messages = [];
  chatState.loading = false;
  chatState.files = [];
  chatState.sendMessage.mockReset().mockResolvedValue(true);
  chatState.getCurrentSessionMessageId.mockReset().mockImplementation(() => `inline-msg-${++nextRequestId}`);
  agentState.loading = false;
  serverRoster = BASE_ROSTER;
  agentState.agents = BASE_ROSTER;
  agentState.fetchAgents.mockReset().mockImplementation(async () => {
    agentState.agents = serverRoster;
  });
  agentState.fetchAgent.mockReset().mockImplementation(async (agentId: string) => agentDetail(agentId));
  mocks.getTemplates.mockReset().mockResolvedValue([TEAM_TEMPLATE, SOLO_TEMPLATE]);
  mocks.instantiateTemplate.mockReset().mockImplementation(async () => {
    serverRoster = [...serverRoster, SUMMONED_AGENT];
    return { id: SUMMONED_AGENT.id };
  });
  mocks.invoke.mockReset().mockResolvedValue(undefined);
  mocks.hideWindow.mockReset().mockResolvedValue(undefined);
  mocks.isTauriRuntime.mockReset().mockReturnValue(false);
}

/** Feeds a chat store change to the subscribers the modal registered. */
export function simulateChatChange(partial: Partial<typeof chatState>): void {
  const previous = { ...chatState };
  Object.assign(chatState, partial);
  for (const listener of hoisted.subscribers) {
    listener(chatState, previous);
  }
}

const CAPTURE: FlowPadCapture = { screenshot: '', windowTitle: 'App', extractedText: 'ctx', timestamp: 1 };

export function openInlinePad(capture: Partial<FlowPadCapture> = {}): void {
  useFlowPadStore.getState().openInline({ ...CAPTURE, ...capture }, 100);
}

export function openChatPad(...captures: Array<Partial<FlowPadCapture>>): void {
  const store = useFlowPadStore.getState();
  store.close();
  store.open();
  captures.forEach((capture, index) => store.addCapture({ ...CAPTURE, timestamp: index + 1, ...capture }));
}

export function renderFlowPad(): ReturnType<typeof render> {
  return render(<FlowPadModal />);
}

export function rerenderFlowPad(view: ReturnType<typeof render>): void {
  view.rerender(<FlowPadModal />);
}

export async function click(element: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(element);
  });
}

export function routeTrigger(): HTMLElement {
  return screen.getByTestId('flowpad-inline-route-trigger');
}

export async function openRouteMenu(): Promise<void> {
  await click(routeTrigger());
}

/** Opens the route menu and picks a roster agent. */
export async function chooseRouteAgent(agentId: string): Promise<void> {
  await openRouteMenu();
  await click(await screen.findByTestId(`flowpad-inline-route-agent-${agentId}`));
}

/** Types into the composer and presses Enter. */
export async function submitText(value: string): Promise<void> {
  const textarea = screen.getByRole('textbox');
  fireEvent.change(textarea, { target: { value } });
  await act(async () => {
    fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter', nativeEvent: { isComposing: false } });
  });
}

/** A promise a test settles by hand. */
export function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (reason: Error) => void } {
  let resolve: (value: T) => void = () => {};
  let reject: (reason: Error) => void = () => {};
  const promise = new Promise<T>((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, resolve, reject };
}
