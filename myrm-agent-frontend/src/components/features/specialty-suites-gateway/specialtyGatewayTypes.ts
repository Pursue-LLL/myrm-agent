/**
 * [INPUT] None (Foundation types for unified specialty workplace hub and mobile pairing gateway)
 * [OUTPUT] SpecialtySuiteItem, EnterpriseConnector, ScheduledJobSummary, MobilePairingSession, CompanionSyncStatus contracts
 * [POS] specialty-suites-gateway/specialtyGatewayTypes.ts
 */

export type SpecialtyDomain = 'finance' | 'legal' | 'data' | 'engineering' | 'operations';

export interface SpecialtySuiteItem {
  id: string;
  name: string;
  domain: SpecialtyDomain;
  description: string;
  iconName: string;
  status: 'active' | 'idle' | 'standby';
  skillsCount: number;
}

export type ConnectorChannel = 'feishu' | 'wechat_work' | 'dingtalk' | 'm365' | 'telegram';

export interface EnterpriseConnector {
  id: string;
  channel: ConnectorChannel;
  displayName: string;
  isConnected: boolean;
  isCloudRelayEnabled: boolean;
  lastActiveTime?: number;
}

export interface ScheduledJobSummary {
  id: string;
  title: string;
  cronExpression: string;
  executionTarget: 'cloud' | 'local_device';
  nextRunTime: number;
  status: 'active' | 'paused';
}

export type PairingStage = 'generating' | 'waiting_scan' | 'scanned' | 'authenticated' | 'expired';

export interface MobilePairingSession {
  sessionId: string;
  channel: ConnectorChannel;
  qrPayload: string;
  ephemeralPublicKey: string;
  stage: PairingStage;
  expiresAt: number;
  deviceLabel?: string;
}

export interface CompanionSyncStatus {
  pairedDeviceId?: string;
  deviceType?: 'ios' | 'android';
  channel: ConnectorChannel;
  isOnline: boolean;
  queuedOfflineTasksCount: number;
  lastSyncTimestamp: number;
}
