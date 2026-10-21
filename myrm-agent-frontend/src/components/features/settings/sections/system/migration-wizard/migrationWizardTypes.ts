/**
 * 本地多生态智能体配置无感扫描与免 SSH 零摩擦迁移向导契约定义
 */

export type EcosystemSource = 'openclaw' | 'hermes' | 'cursor' | 'claude_code';

export interface DetectedAgentAsset {
  id: string;
  source: EcosystemSource;
  originalName: string;
  promptPreview: string;
  modelHint: string;
  selected: boolean;
}

export interface DetectedSkillAsset {
  id: string;
  source: EcosystemSource;
  skillName: string;
  description: string;
  hasScripts: boolean;
  selected: boolean;
}

export interface DetectedMcpAsset {
  id: string;
  source: EcosystemSource;
  serverName: string;
  transportType: 'stdio' | 'sse';
  commandOrUrl: string;
  selected: boolean;
}

export interface ScanRadarReport {
  isScanning: boolean;
  hasDetectedAssets: boolean;
  scannedAt: number;
  agents: DetectedAgentAsset[];
  skills: DetectedSkillAsset[];
  mcpServers: DetectedMcpAsset[];
  totalAssetsCount: number;
}

export type MigrationStatus = 'idle' | 'migrating' | 'completed' | 'error';

export interface MigrationExecutionProgress {
  status: MigrationStatus;
  progressPercentage: number;
  currentStepText: string;
  migratedCount: number;
  errorMessage?: string;
}

export interface MigrationWizardState {
  isBannerVisible: boolean;
  isDrawerOpen: boolean;
  radarReport: ScanRadarReport;
  progress: MigrationExecutionProgress;
}
