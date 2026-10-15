export type HostPlatform = 'macos' | 'windows' | 'linux';

export type HostArchitecture = 'apple_silicon' | 'intel_x64' | 'amd_x64' | 'arm64_pod';

export type HostDeviceKind = 'local_workstation' | 'local_laptop' | 'remote_server' | 'cloud_pod';

export type DeviceHealthStatus = 'online' | 'busy' | 'idle' | 'offline';

export interface HardwareFingerprint {
  deviceId: string;
  hostName: string;
  platform: HostPlatform;
  architecture: HostArchitecture;
  chipModel: string;
  gpuModel?: string;
  kind: HostDeviceKind;
  isCurrentHost: boolean;
}

export interface HostTelemetry {
  cpuUsagePct: number;
  memoryUsagePct: number;
  gpuUsagePct?: number;
  activeTasksCount: number;
  lastHeartbeatMs: number;
  latencyMs: number;
}

export interface HostDevice {
  hardware: HardwareFingerprint;
  telemetry: HostTelemetry;
  status: DeviceHealthStatus;
}

export interface StudioAgentAsset {
  id: string;
  name: string;
  role: string;
  description: string;
  systemPrompt: string;
  boundSkillIds: string[];
  boundConnectorIds: string[];
  boundKnowledgeIds: string[];
  assignedHostDeviceId?: string;
  updatedAtMs: number;
}

export type CallModalityState = 'idle' | 'connecting' | 'active' | 'screen_sharing' | 'ended';

export interface ModalityCallSession {
  sessionId: string;
  agentId: string;
  agentName: string;
  state: CallModalityState;
  isMuted: boolean;
  isSpeakerOn: boolean;
  isScreenSharing: boolean;
  durationSeconds: number;
  enterpriseAuditEnabled: boolean;
  orgId?: string;
}

export interface EnterpriseAuditTrail {
  auditId: string;
  callSessionId: string;
  agentId: string;
  orgId: string;
  timestampMs: number;
  event: 'call_started' | 'screen_share_toggled' | 'call_ended';
  complianceHash: string;
}
