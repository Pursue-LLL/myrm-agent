import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Agent, AgentCreate, AgentListItem, AgentUpdate } from '@/services/agent';
import { deferred } from '@/test-utils/deferred';

const service = vi.hoisted(() => ({
  listAllAgents: vi.fn<() => Promise<AgentListItem[]>>(),
  createAgent: vi.fn<(data: AgentCreate) => Promise<Agent>>(),
  updateAgent: vi.fn<(agentId: string, data: AgentUpdate) => Promise<Agent>>(),
  deleteAgent: vi.fn<(agentId: string) => Promise<void>>(),
  getAgent: vi.fn<(agentId: string, withSecrets: boolean, signal?: AbortSignal) => Promise<Agent>>(),
}));

vi.mock('@/services/agent', () => service);

import useAgentStore from '../useAgentStore';

const STAMP = '2026-01-01T00:00:00Z';

function listItem(id: string, name = id): AgentListItem {
  return { id, name, created_at: STAMP, updated_at: STAMP };
}

function agentRecord(id: string, name = id): Agent {
  return { id, user_id: 'user-1', name, created_at: STAMP, updated_at: STAMP };
}

const store = () => useAgentStore.getState();
const rosterIds = () => store().agents.map((item) => item.id);

beforeEach(() => {
  vi.resetAllMocks();
  useAgentStore.setState({ agents: [], selectedAgent: null, loading: false, error: null });
});

describe('useAgentStore.fetchAgents', () => {
  it('loads the whole roster and ends the load', async () => {
    const load = deferred<AgentListItem[]>();
    service.listAllAgents.mockReturnValue(load.promise);

    const pending = store().fetchAgents();
    expect(store()).toMatchObject({ loading: true, error: null });

    load.resolve([listItem('a'), listItem('b')]);
    await pending;

    expect(store().agents).toEqual([listItem('a'), listItem('b')]);
    expect(store().loading).toBe(false);
  });

  it('does not load again when the roster is already there', async () => {
    useAgentStore.setState({ agents: [listItem('a')] });

    await store().fetchAgents();

    expect(service.listAllAgents).not.toHaveBeenCalled();
    expect(rosterIds()).toEqual(['a']);
  });

  it('shares one request between plain calls made while it runs', async () => {
    const load = deferred<AgentListItem[]>();
    service.listAllAgents.mockReturnValue(load.promise);

    const first = store().fetchAgents();
    const second = store().fetchAgents();
    load.resolve([listItem('a')]);
    await Promise.all([first, second]);

    expect(service.listAllAgents).toHaveBeenCalledTimes(1);
  });

  it('reloads on request even when the roster is present and replaces it', async () => {
    useAgentStore.setState({ agents: [listItem('old')] });
    service.listAllAgents.mockResolvedValue([listItem('a'), listItem('b')]);

    await store().fetchAgents(true);

    expect(service.listAllAgents).toHaveBeenCalledTimes(1);
    expect(rosterIds()).toEqual(['a', 'b']);
  });

  it('keeps the roster and reports the reason when a load fails', async () => {
    useAgentStore.setState({ agents: [listItem('old')] });
    service.listAllAgents.mockRejectedValue(new Error('roster offline'));

    await store().fetchAgents(true);

    expect(store()).toMatchObject({ error: 'roster offline', loading: false });
    expect(rosterIds()).toEqual(['old']);
  });

  it('falls back to a generic message when the failure carries none', async () => {
    service.listAllAgents.mockRejectedValue('boom');

    await store().fetchAgents();

    expect(store().error).toBe('Failed to fetch agents');
    expect(store().loading).toBe(false);
  });

  it('drops the previous error as soon as a new load starts', async () => {
    useAgentStore.setState({ error: 'stale failure' });
    const load = deferred<AgentListItem[]>();
    service.listAllAgents.mockReturnValue(load.promise);

    const pending = store().fetchAgents();
    expect(store().error).toBeNull();

    load.resolve([]);
    await pending;
  });

  describe('when loads overlap', () => {
    function startOverlappingLoads() {
      const older = deferred<AgentListItem[]>();
      const newer = deferred<AgentListItem[]>();
      service.listAllAgents.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
      const olderLoad = store().fetchAgents(true);
      const newerLoad = store().fetchAgents(true);
      return { older, newer, olderLoad, newerLoad };
    }

    it('keeps the newer roster when the older load finishes last', async () => {
      const { older, newer, olderLoad, newerLoad } = startOverlappingLoads();

      newer.resolve([listItem('fresh')]);
      await newerLoad;
      older.resolve([listItem('stale')]);
      await olderLoad;

      expect(rosterIds()).toEqual(['fresh']);
      expect(store()).toMatchObject({ loading: false, error: null });
    });

    it('shows each roster in turn when the loads finish in order', async () => {
      const { older, newer, olderLoad, newerLoad } = startOverlappingLoads();

      older.resolve([listItem('first')]);
      await olderLoad;
      expect(rosterIds()).toEqual(['first']);

      newer.resolve([listItem('second')]);
      await newerLoad;
      expect(rosterIds()).toEqual(['second']);
    });

    it('reports no error for an older load that fails after a newer one succeeded', async () => {
      const { older, newer, olderLoad, newerLoad } = startOverlappingLoads();

      newer.resolve([listItem('fresh')]);
      await newerLoad;
      older.reject(new Error('late failure'));
      await olderLoad;

      expect(rosterIds()).toEqual(['fresh']);
      expect(store().error).toBeNull();
    });

    it('clears an error reported by an older load once the newer one succeeds', async () => {
      const { older, newer, olderLoad, newerLoad } = startOverlappingLoads();

      older.reject(new Error('early failure'));
      await olderLoad;
      expect(store().error).toBe('early failure');

      newer.resolve([listItem('fresh')]);
      await newerLoad;

      expect(rosterIds()).toEqual(['fresh']);
      expect(store().error).toBeNull();
    });
  });
});

describe('useAgentStore.fetchAgent', () => {
  it('selects the loaded agent', async () => {
    service.getAgent.mockResolvedValue(agentRecord('a', 'Agent A'));
    const controller = new AbortController();

    const loaded = await store().fetchAgent('a', controller.signal);

    expect(loaded).toEqual(agentRecord('a', 'Agent A'));
    expect(store().selectedAgent).toEqual(agentRecord('a', 'Agent A'));
    expect(store().loading).toBe(false);
    expect(service.getAgent).toHaveBeenCalledWith('a', false, controller.signal);
  });

  it('ends quietly without touching the selection when the request was aborted', async () => {
    useAgentStore.setState({ selectedAgent: agentRecord('kept') });
    service.getAgent.mockRejectedValue(new DOMException('aborted', 'AbortError'));

    const loaded = await store().fetchAgent('a');

    expect(loaded).toBeNull();
    expect(store()).toMatchObject({ loading: false, error: null });
    expect(store().selectedAgent?.id).toBe('kept');
  });

  it('ends quietly when the caller aborted, whatever the rejection says', async () => {
    const controller = new AbortController();
    controller.abort();
    service.getAgent.mockRejectedValue(new Error('request cancelled'));

    expect(await store().fetchAgent('a', controller.signal)).toBeNull();
    expect(store().error).toBeNull();
  });

  it('records the reason and returns nothing when the load fails', async () => {
    service.getAgent.mockRejectedValue(new Error('agent missing'));

    expect(await store().fetchAgent('a')).toBeNull();
    expect(store()).toMatchObject({ error: 'agent missing', loading: false });
  });

  it('falls back to a generic message when the failure carries none', async () => {
    service.getAgent.mockRejectedValue('boom');

    await store().fetchAgent('a');

    expect(store().error).toBe('Failed to fetch agent');
  });
});

describe('useAgentStore.create', () => {
  it('puts the new agent at the top of the roster', async () => {
    useAgentStore.setState({ agents: [listItem('a')] });
    service.createAgent.mockResolvedValue(agentRecord('new', 'New agent'));

    const created = await store().create({ name: 'New agent' });

    expect(created?.id).toBe('new');
    expect(rosterIds()).toEqual(['new', 'a']);
    expect(store().agents[0]).toMatchObject({ name: 'New agent', created_at: STAMP, updated_at: STAMP });
    expect(store().loading).toBe(false);
  });

  it('leaves the roster alone and reports the reason when creating fails', async () => {
    useAgentStore.setState({ agents: [listItem('a')] });
    service.createAgent.mockRejectedValue(new Error('name taken'));

    expect(await store().create({ name: 'New agent' })).toBeNull();

    expect(rosterIds()).toEqual(['a']);
    expect(store()).toMatchObject({ error: 'name taken', loading: false });
  });

  it('falls back to a generic message when the failure carries none', async () => {
    service.createAgent.mockRejectedValue('boom');

    await store().create({ name: 'New agent' });

    expect(store().error).toBe('Failed to create agent');
  });
});

describe('useAgentStore.update', () => {
  it('refreshes the roster entry and the open agent', async () => {
    useAgentStore.setState({ agents: [listItem('a'), listItem('b')], selectedAgent: agentRecord('a') });
    service.updateAgent.mockResolvedValue(agentRecord('a', 'Renamed'));

    const updated = await store().update('a', { name: 'Renamed' });

    expect(updated?.name).toBe('Renamed');
    expect(store().agents.map((item) => item.name)).toEqual(['Renamed', 'b']);
    expect(store().selectedAgent?.name).toBe('Renamed');
    expect(store().loading).toBe(false);
  });

  it('leaves another open agent and an unlisted agent untouched', async () => {
    useAgentStore.setState({ agents: [listItem('a')], selectedAgent: agentRecord('other') });
    service.updateAgent.mockResolvedValue(agentRecord('unlisted', 'Renamed'));

    await store().update('unlisted', { name: 'Renamed' });

    expect(store().agents).toEqual([listItem('a')]);
    expect(store().selectedAgent?.id).toBe('other');
  });

  it('keeps everything and reports the reason when updating fails', async () => {
    useAgentStore.setState({ agents: [listItem('a')] });
    service.updateAgent.mockRejectedValue(new Error('conflict'));

    expect(await store().update('a', { name: 'Renamed' })).toBeNull();

    expect(store().agents).toEqual([listItem('a')]);
    expect(store()).toMatchObject({ error: 'conflict', loading: false });
  });

  it('falls back to a generic message when the failure carries none', async () => {
    service.updateAgent.mockRejectedValue('boom');

    await store().update('a', { name: 'Renamed' });

    expect(store().error).toBe('Failed to update agent');
  });
});

describe('useAgentStore.remove', () => {
  it('drops the agent from the roster and closes it when it was open', async () => {
    useAgentStore.setState({ agents: [listItem('a'), listItem('b')], selectedAgent: agentRecord('a') });
    service.deleteAgent.mockResolvedValue(undefined);

    expect(await store().remove('a')).toBe(true);

    expect(rosterIds()).toEqual(['b']);
    expect(store().selectedAgent).toBeNull();
    expect(store().loading).toBe(false);
  });

  it('keeps another open agent selected', async () => {
    useAgentStore.setState({ agents: [listItem('a'), listItem('b')], selectedAgent: agentRecord('a') });
    service.deleteAgent.mockResolvedValue(undefined);

    await store().remove('b');

    expect(rosterIds()).toEqual(['a']);
    expect(store().selectedAgent?.id).toBe('a');
  });

  it('keeps the roster and reports the reason when deleting fails', async () => {
    useAgentStore.setState({ agents: [listItem('a')] });
    service.deleteAgent.mockRejectedValue(new Error('agent in use'));

    expect(await store().remove('a')).toBe(false);

    expect(rosterIds()).toEqual(['a']);
    expect(store()).toMatchObject({ error: 'agent in use', loading: false });
  });

  it('falls back to a generic message when the failure carries none', async () => {
    service.deleteAgent.mockRejectedValue('boom');

    await store().remove('a');

    expect(store().error).toBe('Failed to delete agent');
  });
});

describe('useAgentStore selection and error helpers', () => {
  it('sets and clears the open agent', () => {
    store().setSelectedAgent(agentRecord('a'));
    expect(store().selectedAgent?.id).toBe('a');

    store().setSelectedAgent(null);
    expect(store().selectedAgent).toBeNull();
  });

  it('clears the error', () => {
    useAgentStore.setState({ error: 'something failed' });

    store().clearError();

    expect(store().error).toBeNull();
  });
});
