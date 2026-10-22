/**
 * DesktopFloatingPetAndMiniStatusPulseSuite 类型定义
 * 桌面微型悬浮桌宠、状态脉冲、智能体身份投影、语音任务直通与无感数据迁移
 */

export type PetPulseStatus =
  | 'idle'
  | 'thinking'
  | 'working'
  | 'approval_needed'
  | 'done'
  | 'error';

export type PetExpression =
  | 'calm'
  | 'pulsing'
  | 'focused'
  | 'alert_shake'
  | 'celebrate'
  | 'concerned';

export interface AgentIdentityProjection {
  agentId: string;
  name: string;
  colorTheme: string;
  avatarUrl?: string;
  activeRole?: string;
  isPrimary: boolean;
}

export interface SecondaryAgentBadge {
  agentId: string;
  name: string;
  status: 'queued' | 'approving' | 'working';
  colorTheme: string;
}

export interface PetPulseVisualConfig {
  status: PetPulseStatus;
  expression: PetExpression;
  haloColor: string;
  pulseRateHz: number;
  badgeLabel: string;
}

export interface VoiceDirectInputState {
  isRecording: boolean;
  isTranscribing: boolean;
  audioLevel: number;
  durationMs: number;
  error: string | null;
  transcript?: string;
}

export interface VoiceTaskDispatchPayload {
  sessionId?: string;
  targetAgentId?: string;
  prompt: string;
  autoRun: boolean;
  timestamp: number;
}

export type DataMigrationCategory =
  | 'tasks'
  | 'crons'
  | 'memories'
  | 'mcps'
  | 'agents';

export type MigrationSource =
  | 'legacy_myrm'
  | 'hermes'
  | 'cursor'
  | 'openclaw'
  | 'custom_bundle';

export interface MigrationTaskItem {
  id: string;
  title: string;
  prompt: string;
  createdAt: number;
}

export interface MigrationCronItem {
  id: string;
  name: string;
  schedule: string;
  prompt: string;
  enabled: boolean;
}

export interface MigrationMemoryItem {
  id: string;
  key: string;
  value: string;
  category?: string;
}

export interface MigrationMcpItem {
  id: string;
  name: string;
  command: string;
  args?: string[];
  env?: Record<string, string>;
}

export interface MigrationAgentItem {
  id: string;
  name: string;
  systemPrompt: string;
  colorTheme?: string;
}

export interface DataMigrationBundle {
  version: string;
  source: MigrationSource;
  createdAt: number;
  tasks?: MigrationTaskItem[];
  crons?: MigrationCronItem[];
  memories?: MigrationMemoryItem[];
  mcps?: MigrationMcpItem[];
  agents?: MigrationAgentItem[];
}

export type ConflictStrategy = 'overwrite' | 'skip' | 'merge';

export interface MigrationExecutionOptions {
  selectedCategories: DataMigrationCategory[];
  strategy: ConflictStrategy;
}

export interface MigrationReport {
  success: boolean;
  source: MigrationSource;
  importedCounts: Record<DataMigrationCategory, number>;
  skippedCounts: Record<DataMigrationCategory, number>;
  logs: string[];
  timestamp: number;
}

export interface PetApprovalNotice {
  id: string;
  title: string;
  description: string;
  toolName?: string;
  agentId: string;
  agentName: string;
}
