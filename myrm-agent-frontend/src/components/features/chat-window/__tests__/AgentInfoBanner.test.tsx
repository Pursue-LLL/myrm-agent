import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BUILTIN_AGENT_I18N } from '@/components/agent/builtin-agent-i18n-data';
import { deferred } from '@/test-utils/deferred';
import { expectNonNull } from '@/test-utils/expectDefined';
import type { Agent, AgentListItem } from '@/services/agent';
import useAgentStore from '@/store/useAgentStore';
import useChatStore from '@/store/useChatStore';
import AgentInfoBanner from '../AgentInfoBanner';

const kit = vi.hoisted(() => ({
  getAgent: vi.fn<(id: string) => Promise<Agent | null>>(),
  push: vi.fn<(href: string) => void>(),
  toast: vi.fn<(options: { title: string; description?: string; variant?: string }) => void>(),
  fetchAgents: vi.fn<() => Promise<void>>(),
}));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: kit.push }) }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: kit.toast }));
vi.mock('@/services/agent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/agent')>()),
  getAgent: kit.getAgent,
}));

const agent = (id: string, overrides: Partial<Agent> = {}): Agent => ({
  id,
  user_id: 'user-1',
  name: `Agent ${id}`,
  created_at: '2026-01-01',
  updated_at: '2026-01-01',
  ...overrides,
});

const listItem = (id: string): AgentListItem => ({
  id,
  name: `Agent ${id}`,
  created_at: '2026-01-01',
  updated_at: '2026-01-01',
});

const agentsById = new Map<string, Agent>();

async function mount(agentId = 'a', className?: string) {
  const view = render(<AgentInfoBanner agentId={agentId} className={className} />);
  await act(async () => undefined);
  return view;
}

function settingsButton(container: HTMLElement): HTMLElement {
  const button = container.querySelector('.lucide-settings')?.closest('button') ?? null;
  expectNonNull(button, 'settings button');
  return button;
}

/** The roster row of `name` in the open switcher (the banner itself shows the current agent's name as well). */
function rowOf(name: string): HTMLElement {
  const row = screen.getAllByText(name).at(-1)?.closest<HTMLElement>('button') ?? null;
  expectNonNull(row, `row of ${name}`);
  return row;
}

async function openSwitcher(): Promise<void> {
  fireEvent.click(screen.getByRole('button', { name: 'switchButton' }));
  await act(async () => undefined);
}

async function pickInSwitcher(name: string): Promise<void> {
  fireEvent.click(rowOf(name));
  await act(async () => undefined);
}

beforeEach(() => {
  agentsById.clear();
  for (const id of ['a', 'b']) {
    agentsById.set(id, agent(id));
  }
  kit.getAgent.mockImplementation(async (id) => agentsById.get(id) ?? null);
  kit.fetchAgents.mockResolvedValue();
  useAgentStore.setState({ agents: [listItem('a'), listItem('b')], fetchAgents: kit.fetchAgents });
  useChatStore.setState({ loading: false, agentConfig: null });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AgentInfoBanner loading', () => {
  it('shows nothing while the agent is loading', () => {
    kit.getAgent.mockReturnValue(new Promise(() => undefined));
    const { container } = render(<AgentInfoBanner agentId="a" />);

    expect(container).toBeEmptyDOMElement();
  });

  it.each([
    ['cannot be loaded', () => kit.getAgent.mockRejectedValue(new Error('gone'))],
    ['no longer exists', () => kit.getAgent.mockResolvedValue(null)],
  ])('shows nothing when the agent %s', async (_why, arrange) => {
    arrange();
    const { container } = await mount();

    expect(container).toBeEmptyDOMElement();
  });

  it('loads the agent it is given, and the roster for the switcher', async () => {
    await mount('b');

    expect(kit.getAgent).toHaveBeenCalledExactlyOnceWith('b');
    expect(kit.fetchAgents).toHaveBeenCalledTimes(1);
  });

  it('follows the agent when it changes', async () => {
    const { rerender } = await mount('a');

    rerender(<AgentInfoBanner agentId="b" />);
    await act(async () => undefined);

    expect(screen.getByText('Agent b')).toBeInTheDocument();
    expect(screen.queryByText('Agent a')).toBeNull();
  });

  it('ignores an answer for an agent it has already moved away from', async () => {
    const slow = deferred<Agent | null>();
    kit.getAgent.mockReturnValueOnce(slow.promise);
    const { rerender } = render(<AgentInfoBanner agentId="a" />);

    rerender(<AgentInfoBanner agentId="b" />);
    await act(async () => undefined);
    await act(async () => slow.resolve(agent('a')));

    expect(screen.getByText('Agent b')).toBeInTheDocument();
    expect(screen.queryByText('Agent a')).toBeNull();
  });

  it('keeps hiding itself when a late failure arrives for an agent it has moved away from', async () => {
    const slow = deferred<Agent | null>();
    kit.getAgent.mockReturnValueOnce(slow.promise);
    const { rerender } = render(<AgentInfoBanner agentId="a" />);

    rerender(<AgentInfoBanner agentId="b" />);
    await act(async () => undefined);
    await act(async () => slow.reject(new Error('late')));

    expect(screen.getByText('Agent b')).toBeInTheDocument();
  });
});

describe('AgentInfoBanner content', () => {
  it('shows the name, the description and the wiki hint', async () => {
    agentsById.set(
      'a',
      agent('a', { name: 'Researcher', description: 'Reads papers', enabled_builtin_tools: ['wiki'] }),
    );
    await mount();

    expect(screen.getByText('Researcher')).toBeInTheDocument();
    expect(screen.getByText('Reads papers')).toBeInTheDocument();
    expect(screen.getByText('wikiActiveIndicator')).toBeInTheDocument();
  });

  it('leaves out the description and the wiki hint when the agent has neither', async () => {
    agentsById.set('a', agent('a', { name: 'Plain', enabled_builtin_tools: ['web_search'] }));
    const { container } = await mount();

    expect(container.querySelectorAll('p')).toHaveLength(1);
    expect(screen.queryByText('wikiActiveIndicator')).toBeNull();
  });

  it('shows a built-in agent in the language of the interface', async () => {
    const [builtinId, names] = Object.entries(BUILTIN_AGENT_I18N)[0];
    agentsById.set(builtinId, agent(builtinId, { name: 'Raw name', description: 'Raw description' }));
    await mount(builtinId);

    expect(screen.getByText(names.en.name)).toBeInTheDocument();
    expect(screen.queryByText('Raw name')).toBeNull();
  });

  it('takes the class it is given', async () => {
    const { container } = await mount('a', 'custom-class');

    expect(container.firstElementChild).toHaveClass('custom-class');
  });

  it('opens the wiki settings of this agent', async () => {
    agentsById.set('a/1', agent('a/1'));
    const { container } = await mount('a/1');

    fireEvent.click(settingsButton(container));

    expect(kit.push).toHaveBeenCalledExactlyOnceWith('/settings/wiki?agentId=a%2F1');
  });
});

describe('AgentInfoBanner switching agents', () => {
  it('lists the roster, marking the current agent', async () => {
    await mount('a');

    await openSwitcher();

    expect(rowOf('Agent a').querySelector('.lucide-check')).not.toBeNull();
    expect(rowOf('Agent b').querySelector('.lucide-check')).toBeNull();
  });

  it('offers every agent as a real button, so the keyboard works without custom handling', async () => {
    await mount('a');

    await openSwitcher();

    expect(rowOf('Agent b')).toHaveAttribute('type', 'button');
  });

  it('switches the conversation to the chosen agent and confirms', async () => {
    await mount('a');
    await openSwitcher();

    await pickInSwitcher('Agent b');

    expect(kit.getAgent).toHaveBeenLastCalledWith('b');
    expect(useChatStore.getState().agentConfig?.agentId).toBe('b');
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'updateSuccess', description: 'Agent b' });
    expect(screen.queryByText('Agent b')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Agent b/ })).toBeNull();
  });

  it('confirms a switch to a built-in agent by its name in the language of the interface', async () => {
    const [builtinId, names] = Object.entries(BUILTIN_AGENT_I18N)[0];
    agentsById.set(builtinId, agent(builtinId, { name: 'Raw name' }));
    useAgentStore.setState({
      agents: [listItem('a'), { ...listItem(builtinId), name: 'Raw name' }],
      fetchAgents: kit.fetchAgents,
    });
    await mount('a');
    await openSwitcher();

    await pickInSwitcher(names.en.name);

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'updateSuccess', description: names.en.name });
  });

  it('only closes the list when the current agent is chosen again', async () => {
    await mount('a');
    await openSwitcher();
    kit.getAgent.mockClear();

    await pickInSwitcher('Agent a');

    expect(kit.getAgent).not.toHaveBeenCalled();
    expect(useChatStore.getState().agentConfig).toBeNull();
    expect(screen.queryByRole('button', { name: /Agent b/ })).toBeNull();
  });

  it('says so, and changes nothing, when the chosen agent cannot be loaded', async () => {
    await mount('a');
    await openSwitcher();
    kit.getAgent.mockRejectedValueOnce(new Error('offline'));

    await pickInSwitcher('Agent b');

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'switchFailed', variant: 'destructive' });
    expect(useChatStore.getState().agentConfig).toBeNull();
    expect(screen.getByText('Agent a')).toBeInTheDocument();
  });

  it('changes nothing, quietly, when the chosen agent no longer exists', async () => {
    await mount('a');
    await openSwitcher();
    agentsById.delete('b');

    await pickInSwitcher('Agent b');

    expect(kit.toast).not.toHaveBeenCalled();
    expect(useChatStore.getState().agentConfig).toBeNull();
  });

  it('cannot be opened while an answer is streaming', async () => {
    useChatStore.setState({ loading: true });
    await mount('a');

    expect(screen.getByRole('button', { name: 'switchButton' })).toBeDisabled();
  });
});
