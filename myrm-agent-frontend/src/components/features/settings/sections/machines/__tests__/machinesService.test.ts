import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MachinesService } from '../machinesService';

describe('MachinesService', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('listMachines', () => {
    it('returns fetched machines when API response is successful', async () => {
      const mockNodes = [
        {
          machine_id: 'mach-test-01',
          hostname: 'test-node.local',
          display_name: 'Test Node 01',
          platform: 'darwin',
          ip_address: '192.168.1.50',
          status: 'online',
          metrics: {
            cpu_usage_pct: 15.0,
            memory_usage_pct: 30.0,
            disk_usage_pct: 25.0,
            active_tasks_count: 1,
            last_heartbeat_at: '2026-10-13T00:00:00Z',
          },
          registered_at: '2026-10-13T00:00:00Z',
          tags: ['Apple Silicon'],
        },
      ];

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockNodes,
      } as Response);

      const result = await MachinesService.listMachines();
      expect(result).toEqual(mockNodes);
    });

    it('returns realistic mock fleet nodes when API fetch fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'));

      const result = await MachinesService.listMachines();
      expect(result).toHaveLength(2);
      expect(result[0].machine_id).toBe('mach-mac-studio-01');
      expect(result[1].machine_id).toBe('mach-gpu-worker-02');
    });
  });

  describe('generateToken', () => {
    it('returns registration token and command on API success', async () => {
      const mockResponse = {
        token: 'tok-abc-123',
        platform: 'linux' as const,
        quick_command: 'curl -fsSL https://get.myrm.ai/connect.sh | bash',
        expires_at: '2026-10-13T02:00:00Z',
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const result = await MachinesService.generateToken('linux');
      expect(result).toEqual(mockResponse);
    });

    it('generates platform-specific fallback command when API fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('API error'));

      const darwinResult = await MachinesService.generateToken('darwin');
      expect(darwinResult.quick_command).toContain('curl -fsSL https://get.myrm.ai/connect.sh');
      expect(darwinResult.token).toMatch(/^tok-mock-/);

      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('API error'));
      const winResult = await MachinesService.generateToken('windows');
      expect(winResult.quick_command).toContain('powershell -ExecutionPolicy Bypass');
    });
  });

  describe('initiateTakeover and releaseTakeover', () => {
    it('initiates takeover and returns session', async () => {
      const mockSession = {
        session_id: 'session-tk-01',
        machine_id: 'mach-01',
        state: 'human_takeover' as const,
        operator_id: 'user-primary',
        started_at: '2026-10-13T00:00:00Z',
        updated_at: '2026-10-13T00:00:00Z',
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockSession,
      } as Response);

      const result = await MachinesService.initiateTakeover('mach-01', 'user-primary');
      expect(result).toEqual(mockSession);
    });

    it('releases takeover back to agent', async () => {
      const mockSession = {
        session_id: 'session-tk-02',
        machine_id: 'mach-01',
        state: 'agent' as const,
        started_at: '2026-10-13T00:00:00Z',
        updated_at: '2026-10-13T00:00:00Z',
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockSession,
      } as Response);

      const result = await MachinesService.releaseTakeover('mach-01');
      expect(result.state).toBe('agent');
    });

    it('returns local takeover session fallback when fetch fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'));

      const result = await MachinesService.initiateTakeover('mach-99', 'dev-operator');
      expect(result.state).toBe('human_takeover');
      expect(result.operator_id).toBe('dev-operator');
      expect(result.machine_id).toBe('mach-99');
    });
  });
});
