import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Agent, CommandBindingConfig } from '@/services/agent';
import { useAgentCommandBindings } from '../useAgentCommandBindings';

const { getAgentMock, updateAgentMock } = vi.hoisted(() => ({
  getAgentMock: vi.fn(),
  updateAgentMock: vi.fn(),
}));

vi.mock('@/services/agent', () => ({ getAgent: getAgentMock, updateAgent: updateAgentMock }));

const REPORT: CommandBindingConfig = { command_name: 'report', skill_ids: ['skill-a'] };
const SERVER_REPORT: CommandBindingConfig = {
  ...REPORT,
  description: '',
  aliases: [],
  instruction: '',
};

const agentWith = (bindings: CommandBindingConfig[] | null | undefined) =>
  ({ id: 'agent-1', command_bindings: bindings }) as Agent;

function mount(initial: { agentId?: string | null; isNew?: boolean; editorLoading?: boolean } = {}) {
  return renderHook(
    (props: { agentId: string | null; isNew: boolean; editorLoading: boolean }) =>
      useAgentCommandBindings(props.agentId, props.isNew, props.editorLoading),
    { initialProps: { agentId: 'agent-1', isNew: false, editorLoading: false, ...initial } },
  );
}

async function mountReady(bindings: CommandBindingConfig[] | null | undefined = [REPORT]) {
  getAgentMock.mockResolvedValue(agentWith(bindings));
  const view = mount();
  await waitFor(() => expect(view.result.current.status).toBe('ready'));
  return view;
}

describe('useAgentCommandBindings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads the persisted bindings with server defaults filled in, without marking them dirty', async () => {
    const { result } = await mountReady([REPORT]);

    expect(result.current.bindings).toEqual([SERVER_REPORT]);
    expect(result.current.dirty).toBe(false);
    expect(result.current.canSave).toBe(true);
  });

  it('treats a null binding list as empty', async () => {
    const { result } = await mountReady(null);

    expect(result.current.bindings).toEqual([]);
  });

  it('does not load or allow saving for an agent that does not exist yet', () => {
    const { result } = mount({ agentId: null, isNew: true });

    expect(result.current.unavailable).toBe(true);
    expect(result.current.dirty).toBe(false);
    expect(result.current.canSave).toBe(false);
    expect(getAgentMock).not.toHaveBeenCalled();
  });

  it('waits for the editor to finish loading, then reloads whenever the editor reloads', async () => {
    getAgentMock.mockResolvedValue(agentWith([REPORT]));
    const view = mount({ editorLoading: true });
    expect(getAgentMock).not.toHaveBeenCalled();

    view.rerender({ agentId: 'agent-1', isNew: false, editorLoading: false });
    await waitFor(() => expect(view.result.current.status).toBe('ready'));
    expect(getAgentMock).toHaveBeenCalledTimes(1);

    act(() => view.result.current.setBindings([REPORT, { command_name: 'extra', skill_ids: ['skill-b'] }]));
    expect(view.result.current.dirty).toBe(true);

    getAgentMock.mockResolvedValue(agentWith([{ ...REPORT, command_name: 'restored' }]));
    view.rerender({ agentId: 'agent-1', isNew: false, editorLoading: true });
    view.rerender({ agentId: 'agent-1', isNew: false, editorLoading: false });
    await waitFor(() => expect(view.result.current.bindings[0]?.command_name).toBe('restored'));
    expect(getAgentMock).toHaveBeenCalledTimes(2);
    expect(view.result.current.bindings).toHaveLength(1);
    expect(view.result.current.dirty).toBe(false);
  });

  it('refuses to save when loading failed, so an empty draft cannot wipe server-side bindings', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    getAgentMock.mockRejectedValue(new Error('offline'));
    const view = mount();
    await waitFor(() => expect(view.result.current.status).toBe('error'));

    act(() => view.result.current.setBindings([REPORT]));
    expect(view.result.current.dirty).toBe(false);
    expect(view.result.current.canSave).toBe(false);
    await act(() => view.result.current.save());
    expect(updateAgentMock).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it('flags incomplete drafts and refuses to save them', async () => {
    const { result } = await mountReady([REPORT]);

    act(() => result.current.setBindings([REPORT, { command_name: '', skill_ids: [] }]));

    expect(result.current.issues).toEqual([null, 'incomplete']);
    expect(result.current.dirty).toBe(true);
    expect(result.current.canSave).toBe(false);
    await act(() => result.current.save());
    expect(updateAgentMock).not.toHaveBeenCalled();
  });

  it('persists edits as an explicit command_bindings key and adopts the server copy as the new baseline', async () => {
    const { result } = await mountReady([REPORT]);
    const edited = { command_name: 'Summary', skill_ids: ['skill-a', 'skill-b'] };
    const serverCopy = {
      command_name: 'summary',
      skill_ids: ['skill-a', 'skill-b'],
      description: '',
      aliases: [],
      instruction: '',
    };
    updateAgentMock.mockResolvedValue(agentWith([serverCopy]));

    act(() => result.current.setBindings([edited]));
    await act(() => result.current.save());

    expect(updateAgentMock).toHaveBeenCalledWith('agent-1', {
      command_bindings: [{ ...edited, description: '', aliases: [], instruction: '' }],
    });
    expect(result.current.bindings).toEqual([serverCopy]);
    expect(result.current.dirty).toBe(false);
    expect(result.current.saving).toBe(false);
  });

  it('clears the server bindings with an explicit null when every binding is removed', async () => {
    const { result } = await mountReady([REPORT]);
    updateAgentMock.mockResolvedValue(agentWith(null));

    act(() => result.current.setBindings([]));
    await act(() => result.current.save());

    expect(updateAgentMock).toHaveBeenCalledWith('agent-1', { command_bindings: null });
    expect(result.current.dirty).toBe(false);
    expect(result.current.bindings).toEqual([]);
  });

  it('does not send a request when nothing changed', async () => {
    const { result } = await mountReady([REPORT]);

    await act(() => result.current.save());

    expect(updateAgentMock).not.toHaveBeenCalled();
  });

  it('keeps the draft dirty and rethrows so the caller can report it when the update fails', async () => {
    const { result } = await mountReady([REPORT]);
    updateAgentMock.mockRejectedValue(new Error('boom'));

    act(() => result.current.setBindings([]));
    await act(async () => {
      await expect(result.current.save()).rejects.toThrow('boom');
    });

    expect(result.current.dirty).toBe(true);
    expect(result.current.saving).toBe(false);
  });

  it('keeps edits made while a save is in flight and only moves the saved baseline', async () => {
    const { result } = await mountReady([REPORT]);
    let resolveUpdate: (agent: Agent) => void = () => {};
    updateAgentMock.mockReturnValue(new Promise<Agent>((resolve) => (resolveUpdate = resolve)));

    act(() => result.current.setBindings([]));
    let pending = Promise.resolve();
    act(() => {
      pending = result.current.save();
    });
    const newer = { command_name: 'newer', skill_ids: ['skill-z'] };
    act(() => result.current.setBindings([newer]));
    await act(async () => {
      resolveUpdate(agentWith(null));
      await pending;
    });

    expect(result.current.bindings).toEqual([newer]);
    expect(result.current.dirty).toBe(true);
  });
});
