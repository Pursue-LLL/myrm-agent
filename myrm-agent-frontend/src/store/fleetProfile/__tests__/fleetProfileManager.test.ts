import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FleetProfileManager } from '../fleetProfileManager';
import { FleetSwitchEvent, ProfileHealthStatus } from '../fleetProfileTypes';

describe('FleetProfileManager', () => {
  let manager: FleetProfileManager;

  beforeEach(() => {
    manager = FleetProfileManager.getInstance();
    manager.resetForTesting();
  });

  it('should register profiles and automatically elect default active profile', () => {
    const p1 = manager.addProfile({
      id: 'local-dev',
      name: 'Local Dev Server',
      baseUrl: 'http://localhost:8080',
      environmentKind: 'local',
      isDefault: true,
    });

    const p2 = manager.addProfile({
      id: 'homelab-box',
      name: 'Homelab Server',
      baseUrl: 'http://homelab.local:8080',
      environmentKind: 'homelab',
    });

    expect(manager.listProfiles()).toHaveLength(2);
    expect(manager.getActiveProfile()?.id).toBe('local-dev');
    expect(manager.getProfile('homelab-box')?.name).toBe('Homelab Server');
  });

  it('should support zero-reload seamless hot-switching with event notification', async () => {
    manager.addProfile({
      id: 'local-dev',
      name: 'Local Dev',
      baseUrl: 'http://localhost:8080',
      environmentKind: 'local',
    });
    manager.addProfile({
      id: 'cloud-vps',
      name: 'Cloud VPS',
      baseUrl: 'https://vps.myrm.io',
      environmentKind: 'vps',
    });

    const switchSpy = vi.fn<(event: FleetSwitchEvent) => void>();
    const unsubscribe = manager.onProfileSwitch(switchSpy);

    const switched = await manager.switchProfile('cloud-vps');
    expect(switched.id).toBe('cloud-vps');
    expect(manager.getActiveProfile()?.id).toBe('cloud-vps');
    expect(switchSpy).toHaveBeenCalledTimes(1);
    expect(switchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        previousProfileId: 'local-dev',
        activeProfile: expect.objectContaining({ id: 'cloud-vps' }),
      })
    );

    unsubscribe();
  });

  it('should prevent deleting currently active profile', () => {
    manager.addProfile({
      id: 'active-node',
      name: 'Active Node',
      baseUrl: 'http://localhost:8080',
      environmentKind: 'local',
      isDefault: true,
    });

    expect(() => manager.removeProfile('active-node')).toThrowError(
      'Cannot remove currently active profile "active-node". Switch first.'
    );
  });

  it('should probe health and compute RTT accurately', async () => {
    manager.addProfile({
      id: 'target-node',
      name: 'Target Node',
      baseUrl: 'http://target:8080',
      environmentKind: 'vps',
    });

    const healthSpy = vi.fn<(status: ProfileHealthStatus) => void>();
    manager.onHealthChange(healthSpy);

    const status = await manager.probeHealth('target-node', async () => {
      return { ok: true, rttMs: 28 };
    });

    expect(status.isOnline).toBe(true);
    expect(status.rttMs).toBe(28);
    expect(healthSpy).toHaveBeenCalledTimes(1);
    expect(manager.getHealthStatus('target-node')?.rttMs).toBe(28);
  });

  it('should buffer offline actions and flush upon network reconnection', async () => {
    manager.addProfile({
      id: 'edge-box',
      name: 'Edge Box',
      baseUrl: 'http://edge:8080',
      environmentKind: 'cloud_sandbox',
    });

    const queued1 = manager.enqueueOfflineAction({
      profileId: 'edge-box',
      actionType: 'sendMessage',
      payload: { text: 'Hello edge' },
    });
    const queued2 = manager.enqueueOfflineAction({
      profileId: 'edge-box',
      actionType: 'triggerRun',
      payload: { runId: 'run-001' },
    });

    expect(manager.getQueuedActions()).toHaveLength(2);
    expect(queued1.actionType).toBe('sendMessage');

    const executedActions: string[] = [];
    const flushResult = await manager.flushOfflineQueue(async (action) => {
      executedActions.push(action.actionType);
      return true;
    });

    expect(flushResult.dispatched).toBe(2);
    expect(flushResult.failed).toBe(0);
    expect(executedActions).toEqual(['sendMessage', 'triggerRun']);
    expect(manager.getQueuedActions()).toHaveLength(0);
  });
});
