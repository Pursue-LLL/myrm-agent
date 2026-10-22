/**
 * Types and schema contracts for Self-Hosted Machine Fleet & Live Screen Takeover.
 * Adheres to Cursor "My Machines" & Live Takeover paradigm with zero emojis.
 */

export type MachinePlatform = 'darwin' | 'linux' | 'windows';

export type MachineStatus = 'online' | 'busy' | 'offline' | 'takeover';

export interface MachineMetrics {
  cpu_usage_pct: number;
  memory_usage_pct: number;
  disk_usage_pct: number;
  active_tasks_count: number;
  last_heartbeat_at: string;
}

export interface MachineNode {
  machine_id: string;
  hostname: string;
  display_name: string;
  platform: MachinePlatform;
  ip_address: string;
  status: MachineStatus;
  metrics: MachineMetrics;
  registered_at: string;
  tags: string[];
  screen_stream_url?: string;
}

export interface RegistrationTokenResponse {
  token: string;
  platform: MachinePlatform;
  quick_command: string;
  expires_at: string;
}

export type TakeoverState = 'agent' | 'human_takeover';

export interface TakeoverSession {
  session_id: string;
  machine_id: string;
  state: TakeoverState;
  operator_id?: string;
  started_at: string;
  updated_at: string;
}
