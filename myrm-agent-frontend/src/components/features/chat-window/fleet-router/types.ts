export type GatewayPlatformType = 'darwin' | 'linux' | 'vps' | 'cloud';

export type GatewayStatusType = 'online' | 'offline' | 'degraded';

export interface GatewayTelemetry {
  cpu_pct: number;
  mem_pct: number;
  active_agents: number;
  queue_depth: number;
}

export interface GatewayNode {
  gateway_id: string;
  label: string;
  host: string;
  port: number;
  protocol: string;
  platform: GatewayPlatformType;
  status: GatewayStatusType;
  latency_ms: number;
  telemetry: GatewayTelemetry;
  last_heartbeat: number;
}

export interface FleetProfile {
  profile_id: string;
  gateway_id: string;
  name: string;
  avatar: string;
  role: string;
  system_context: string;
  is_active: boolean;
}

export interface OfflineBufferedCommand {
  command_id: string;
  gateway_id: string;
  profile_id: string;
  command_type: string;
  payload: Record<string, string>;
  queued_at: number;
  retry_count: number;
}

export interface RelayedArtifact {
  artifact_id: string;
  source_gateway: string;
  target_gateway: string;
  name: string;
  file_path: string;
  sha256: string;
  chunk_data: string;
  created_at: number;
  is_verified: boolean;
}

export interface FleetRailState {
  gateways: Record<string, GatewayNode>;
  profiles: Record<string, FleetProfile>;
  buffered_commands: Record<string, OfflineBufferedCommand[]>;
  active_profile_id: string | null;
  updated_at: number;
}

export const DEFAULT_FLEET_STATE: FleetRailState = {
  gateways: {
    'gw-mac-local': {
      gateway_id: 'gw-mac-local',
      label: 'MacBook Pro Host',
      host: '127.0.0.1',
      port: 8080,
      protocol: 'ws',
      platform: 'darwin',
      status: 'online',
      latency_ms: 1.2,
      telemetry: {
        cpu_pct: 14.5,
        mem_pct: 38.0,
        active_agents: 2,
        queue_depth: 0,
      },
      last_heartbeat: 1710000000,
    },
    'gw-cloud-gpu': {
      gateway_id: 'gw-cloud-gpu',
      label: 'Ubuntu GPU Cluster',
      host: '10.0.4.15',
      port: 9090,
      protocol: 'wss',
      platform: 'linux',
      status: 'online',
      latency_ms: 28.4,
      telemetry: {
        cpu_pct: 68.0,
        mem_pct: 75.5,
        active_agents: 5,
        queue_depth: 2,
      },
      last_heartbeat: 1710000000,
    },
    'gw-vps-edge': {
      gateway_id: 'gw-vps-edge',
      label: 'Tokyo VPS Relay',
      host: '157.7.20.88',
      port: 8080,
      protocol: 'wss',
      platform: 'vps',
      status: 'offline',
      latency_ms: 0.0,
      telemetry: {
        cpu_pct: 0.0,
        mem_pct: 0.0,
        active_agents: 0,
        queue_depth: 0,
      },
      last_heartbeat: 1709990000,
    },
  },
  profiles: {
    'prof-orch-lead': {
      profile_id: 'prof-orch-lead',
      gateway_id: 'gw-mac-local',
      name: 'Primary Orchestrator',
      avatar: '🧭',
      role: 'Fleet Dispatcher',
      system_context: 'Coordinate user requests across all fleet nodes.',
      is_active: true,
    },
    'prof-gpu-coder': {
      profile_id: 'prof-gpu-coder',
      gateway_id: 'gw-cloud-gpu',
      name: 'DeepCoder V2',
      avatar: '⚡',
      role: 'High-Throughput Coder',
      system_context: 'Execute parallel code compilation and heavy inference.',
      is_active: false,
    },
    'prof-vps-scraper': {
      profile_id: 'prof-vps-scraper',
      gateway_id: 'gw-vps-edge',
      name: 'Tokyo Crawler',
      avatar: '🌐',
      role: 'Remote Data Fetcher',
      system_context: 'Fetch web data from low-latency Asia-Pacific IP.',
      is_active: false,
    },
  },
  buffered_commands: {
    'gw-vps-edge': [
      {
        command_id: 'cmd-buf-101',
        gateway_id: 'gw-vps-edge',
        profile_id: 'prof-vps-scraper',
        command_type: 'fetch_feed',
        payload: { target: 'https://api.nikkei.com/market' },
        queued_at: 1710000010,
        retry_count: 1,
      },
    ],
  },
  active_profile_id: 'prof-orch-lead',
  updated_at: 1710000000,
};
