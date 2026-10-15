export type CommandCenterTab = 'sessions' | 'system' | 'usage' | 'maintenance';

export type HealthStatusType = 'healthy' | 'warning' | 'degraded';

export type LogComponent = 'agent' | 'gateway' | 'error' | 'desktop';

export type LogLevel = 'info' | 'warn' | 'error' | 'debug';

export interface SessionSummaryItem {
  id: string;
  title: string;
  agentName: string;
  updatedAt: string;
  messageCount: number;
  tokenCount: number;
  isPinned: boolean;
  tags: string[];
}

export interface GatewayHealthState {
  isRunning: boolean;
  latencyMs: number;
  version: string;
  activeSessionsCount: number;
  serverType: 'local_python' | 'desktop_sidecar' | 'cloud_sandbox';
  status: HealthStatusType;
}

export interface CommandCenterLogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  component: LogComponent;
  message: string;
}

export type UsageHorizon = 7 | 30 | 90;

export interface ModelUsageItem {
  modelId: string;
  modelName: string;
  tokenCount: number;
  percentage: number;
  costEstimateUsd: number;
}

export interface SkillActionItem {
  skillId: string;
  skillName: string;
  actionCount: number;
  successRate: number;
}

export interface UsageSummary {
  horizonDays: UsageHorizon;
  totalSessions: number;
  totalApiCalls: number;
  tokensIn: number;
  tokensOut: number;
  topModels: ModelUsageItem[];
  topSkills: SkillActionItem[];
}

export type MaintenanceActionType =
  | 'doctor'
  | 'security_audit'
  | 'backup_sqlite'
  | 'debug_share'
  | 'skill_curator'
  | 'memory_reset';

export interface MaintenanceTaskState {
  action: MaintenanceActionType | null;
  status: 'idle' | 'running' | 'success' | 'failed';
  message: string;
  progressPercent: number;
}

export interface SessionAuditPackPayload {
  sessionId: string;
  title: string;
  generatedAt: string;
  exportFormat: 'markdown' | 'json';
  summaryMarkdown: string;
  rawJsonData: string;
}
