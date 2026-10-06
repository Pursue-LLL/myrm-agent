/**
 * Data contracts and definitions for Multi-Server Fleet Profiles and Gateway Manager.
 */

export type FleetEnvironmentKind = 'local' | 'homelab' | 'vps' | 'cloud_sandbox';

export interface ServerFleetProfile {
  id: string;
  name: string;
  baseUrl: string;
  wsUrl?: string;
  token?: string;
  environmentKind: FleetEnvironmentKind;
  isDefault?: boolean;
  createdAt: number;
}

export interface ProfileHealthStatus {
  profileId: string;
  isOnline: boolean;
  rttMs: number;
  lastCheckedAt: number;
  errorMessage?: string;
}

export interface OfflineQueuedAction {
  id: string;
  profileId: string;
  actionType: string;
  payload: Record<string, unknown>;
  enqueuedAt: number;
  retryCount: number;
}

export interface FleetSwitchEvent {
  previousProfileId: string | null;
  activeProfile: ServerFleetProfile;
  timestamp: number;
}

export type ProfileSwitchListener = (event: FleetSwitchEvent) => void;
export type HealthChangeListener = (status: ProfileHealthStatus) => void;
export type OfflineFlushListener = (actions: readonly OfflineQueuedAction[]) => void;
