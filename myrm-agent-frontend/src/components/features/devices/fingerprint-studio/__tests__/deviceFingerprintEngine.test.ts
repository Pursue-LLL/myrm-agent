import { describe, it, expect } from 'vitest';
import {
  formatDeviceLabel,
  formatHardwareBadge,
  computeDeviceHealth,
  buildDeviceFingerprintHash,
  createEnterpriseAuditRecord,
} from '../deviceFingerprintEngine';
import { HostDevice, ModalityCallSession } from '../fingerprintStudioTypes';

describe('deviceFingerprintEngine', () => {
  const mockDevice: HostDevice = {
    hardware: {
      deviceId: 'host_mac_test',
      hostName: 'Studio-MacBook',
      platform: 'macos',
      architecture: 'apple_silicon',
      chipModel: 'Apple M3 Pro',
      kind: 'local_laptop',
      isCurrentHost: true,
    },
    telemetry: {
      cpuUsagePct: 20,
      memoryUsagePct: 30,
      gpuUsagePct: 10,
      activeTasksCount: 0,
      lastHeartbeatMs: 1000000,
      latencyMs: 5,
    },
    status: 'online',
  };

  it('formats device label correctly with and without GPU', () => {
    expect(formatDeviceLabel(mockDevice)).toBe('Studio-MacBook (Apple M3 Pro)');

    const winDevice: HostDevice = {
      ...mockDevice,
      hardware: {
        ...mockDevice.hardware,
        hostName: 'Workstation',
        platform: 'windows',
        architecture: 'amd_x64',
        chipModel: 'Ryzen 9',
        gpuModel: 'RTX 4090',
      },
    };
    expect(formatDeviceLabel(winDevice)).toBe('Workstation (Ryzen 9 · RTX 4090)');
  });

  it('formats hardware badge info across different platforms and kinds', () => {
    const badge = formatHardwareBadge(mockDevice.hardware);
    expect(badge.title).toBe('Studio-MacBook [MACOS]');
    expect(badge.subtitle).toBe('Apple M3 Pro');
    expect(badge.tag).toBe('Local');

    const podBadge = formatHardwareBadge({
      ...mockDevice.hardware,
      kind: 'cloud_pod',
      platform: 'linux',
      hostName: 'K8s-Pod-01',
    });
    expect(podBadge.title).toBe('K8s-Pod-01 [LINUX]');
    expect(podBadge.tag).toBe('Cloud Pod');
  });

  it('computes device health status and congestion correctly', () => {
    // 正常在线状态
    const now = 1000000;
    const health = computeDeviceHealth(mockDevice.telemetry, now);
    expect(health.status).toBe('online');
    expect(health.isCongested).toBe(false);

    // 高负载与排队任务
    const busyTelemetry = {
      ...mockDevice.telemetry,
      cpuUsagePct: 90,
      memoryUsagePct: 88,
      gpuUsagePct: 95,
      activeTasksCount: 5,
    };
    const congestedHealth = computeDeviceHealth(busyTelemetry, now);
    expect(congestedHealth.status).toBe('busy');
    expect(congestedHealth.isCongested).toBe(true);
    expect(congestedHealth.loadScore).toBeGreaterThanOrEqual(85);

    // 心跳超时判定离线
    const offlineHealth = computeDeviceHealth(mockDevice.telemetry, now + 40000, 30000);
    expect(offlineHealth.status).toBe('offline');
    expect(offlineHealth.loadScore).toBe(0);
  });

  it('builds deterministic device fingerprint hash', () => {
    const hash1 = buildDeviceFingerprintHash(mockDevice.hardware);
    const hash2 = buildDeviceFingerprintHash(mockDevice.hardware);
    expect(hash1).toBe(hash2);
    expect(hash1.startsWith('fp_mac_')).toBe(true);
  });

  it('generates enterprise audit record with verifiable compliance hash', () => {
    const session: ModalityCallSession = {
      sessionId: 'call_test_1',
      agentId: 'agent_fullstack',
      agentName: '架构专家',
      state: 'active',
      isMuted: false,
      isSpeakerOn: true,
      isScreenSharing: false,
      durationSeconds: 120,
      enterpriseAuditEnabled: true,
      orgId: 'org-acme-corp',
    };

    const audit = createEnterpriseAuditRecord(session, 'call_started', 1700000000000);
    expect(audit.callSessionId).toBe('call_test_1');
    expect(audit.orgId).toBe('org-acme-corp');
    expect(audit.event).toBe('call_started');
    expect(audit.complianceHash.startsWith('AUDIT-SHA256-')).toBe(true);
  });
});
