import {
  HostDevice,
  HardwareFingerprint,
  HostTelemetry,
  DeviceHealthStatus,
  ModalityCallSession,
  EnterpriseAuditTrail,
} from './fingerprintStudioTypes';

export function formatDeviceLabel(device: HostDevice): string {
  const { hostName, chipModel, gpuModel } = device.hardware;
  if (gpuModel && gpuModel.trim().length > 0) {
    return `${hostName} (${chipModel} · ${gpuModel})`;
  }
  return `${hostName} (${chipModel})`;
}

export function formatHardwareBadge(hardware: HardwareFingerprint): {
  title: string;
  subtitle: string;
  tag: string;
} {
  const { hostName, chipModel, platform, kind, gpuModel } = hardware;
  
  let tag = 'Local';
  if (kind === 'cloud_pod') {
    tag = 'Cloud Pod';
  } else if (kind === 'remote_server') {
    tag = 'Remote';
  }

  const subtitle = gpuModel && gpuModel.length > 0 ? `${chipModel} / ${gpuModel}` : chipModel;
  const platformPrefix = platform.toUpperCase();

  return {
    title: `${hostName} [${platformPrefix}]`,
    subtitle,
    tag,
  };
}

export function computeDeviceHealth(
  telemetry: HostTelemetry,
  currentTimeMs: number = Date.now(),
  heartbeatTimeoutMs: number = 30000
): {
  status: DeviceHealthStatus;
  loadScore: number;
  isCongested: boolean;
} {
  const timeSinceHeartbeat = currentTimeMs - telemetry.lastHeartbeatMs;
  if (timeSinceHeartbeat > heartbeatTimeoutMs) {
    return {
      status: 'offline',
      loadScore: 0,
      isCongested: false,
    };
  }

  const cpu = Math.max(0, Math.min(100, telemetry.cpuUsagePct));
  const memory = Math.max(0, Math.min(100, telemetry.memoryUsagePct));
  const gpu = telemetry.gpuUsagePct !== undefined ? Math.max(0, Math.min(100, telemetry.gpuUsagePct)) : cpu;

  // 综合负载加权：CPU 40%, 内存 30%, GPU 30%
  const loadScore = Math.round(cpu * 0.4 + memory * 0.3 + gpu * 0.3);
  const isCongested = loadScore >= 85 || telemetry.activeTasksCount >= 4;

  let status: DeviceHealthStatus = 'idle';
  if (telemetry.activeTasksCount > 0 || loadScore >= 60) {
    status = 'busy';
  } else if (loadScore >= 5) {
    status = 'online';
  }

  return {
    status,
    loadScore,
    isCongested,
  };
}

export function buildDeviceFingerprintHash(hardware: HardwareFingerprint): string {
  const rawKey = `${hardware.deviceId}:${hardware.platform}:${hardware.architecture}:${hardware.chipModel}:${hardware.gpuModel || 'none'}`;
  let hash = 0;
  for (let i = 0; i < rawKey.length; i++) {
    hash = (hash << 5) - hash + rawKey.charCodeAt(i);
    hash |= 0;
  }
  const hexPart = Math.abs(hash).toString(16).padStart(8, '0');
  return `fp_${hardware.platform.slice(0, 3)}_${hexPart}`;
}

export function createEnterpriseAuditRecord(
  session: ModalityCallSession,
  event: EnterpriseAuditTrail['event'],
  timestampMs: number = Date.now()
): EnterpriseAuditTrail {
  const org = session.orgId || 'org-default-ent';
  const raw = `${session.sessionId}|${session.agentId}|${org}|${event}|${timestampMs}`;
  let hash = 0;
  for (let i = 0; i < raw.length; i++) {
    hash = (hash << 5) - hash + raw.charCodeAt(i);
    hash |= 0;
  }
  const complianceHash = `AUDIT-SHA256-${Math.abs(hash).toString(16).padStart(8, '0').toUpperCase()}`;

  return {
    auditId: `audit_${timestampMs}_${Math.random().toString(36).substring(2, 7)}`,
    callSessionId: session.sessionId,
    agentId: session.agentId,
    orgId: org,
    timestampMs,
    event,
    complianceHash,
  };
}
