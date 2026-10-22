/**
 * 多源旧版智能体资产静默迁移与一键对账导入数据模型
 */

export type MigrationSourceType =
  | 'qoder_v1'
  | 'hermes_legacy'
  | 'openclaw'
  | 'sqlite_backup'
  | 'custom_json';

export type ConflictStrategy = 'skip' | 'overwrite' | 'rename';

export interface LegacyTaskItem {
  id: string;
  title: string;
  description?: string;
  createdAt: number;
  status: 'completed' | 'pending' | 'failed';
  tags?: string[];
}

export interface LegacyCronJob {
  id: string;
  name: string;
  cronExpression: string;
  taskTemplate: string;
  enabled: boolean;
  nextRunTime?: number;
}

export interface LegacyMemoryItem {
  id: string;
  category: 'profile' | 'preference' | 'project';
  content: string;
  confidence: number;
  createdAt: number;
}

export interface LegacyMcpConfig {
  name: string;
  transport: 'stdio' | 'sse';
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  enabled: boolean;
}

export interface FourDimensionalAssets {
  tasks: LegacyTaskItem[];
  cronJobs: LegacyCronJob[];
  memories: LegacyMemoryItem[];
  mcpConfigs: LegacyMcpConfig[];
}

export interface AssetCategoryStats {
  total: number;
  newCount: number;
  duplicateCount: number;
}

export interface MigrationReconciliationReport {
  batchId: string;
  sourceType: MigrationSourceType;
  sourcePath?: string;
  detectedAt: number;
  tasks: AssetCategoryStats;
  cronJobs: AssetCategoryStats;
  memories: AssetCategoryStats;
  mcpConfigs: AssetCategoryStats;
  conflictStrategy: ConflictStrategy;
}

export type MigrationStatus =
  | 'idle'
  | 'scanning'
  | 'reconciling'
  | 'importing'
  | 'completed'
  | 'failed';

export interface MigrationLogEntry {
  id: string;
  timestamp: number;
  level: 'info' | 'warn' | 'error';
  message: string;
}
