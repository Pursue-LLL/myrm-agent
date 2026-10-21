/**
 * 桌面端零越界用户授权契约、全链路 Token 成本透明沙盒与微差量热更套件契约
 */

export type AutostartAuthorizationState = 'not_prompted' | 'granted' | 'denied';

export interface DaemonProcessMetrics {
  pid: number;
  cpuUsagePercent: number;
  memoryUsageMb: number;
  networkTxKb: number;
  uptimeSeconds: number;
  isZombieCleaned: boolean;
}

export interface CostBudgetGateConfig {
  estimatedTokens: number;
  estimatedCostUsd: number;
  thresholdUsd: number;
  isGateConfirmed: boolean;
  actualTokensUsed: number;
  actualCostUsd: number;
}

export interface AntiDowngradeTelemetry {
  physicalModelId: string;
  claimedModelId: string;
  provider: string;
  latencyMs: number;
  isDowngradeDetected: boolean;
}

export interface StepSaverMetrics {
  savedSteps: string[];
  estimatedMinutesSaved: number;
  honestBoundaryNotice: string;
}

export interface MicroDeltaOtaInfo {
  patchSizeKb: number;
  fullPackageSizeMb: number;
  bandwidthSavedPercent: number;
  versionTag: string;
  status: 'up_to_date' | 'downloading_delta' | 'ready_to_apply';
}

export interface ZeroTrespassSuiteState {
  autostartAuth: AutostartAuthorizationState;
  neverOverrideSystemChoice: boolean;
  daemonMetrics: DaemonProcessMetrics;
  costBudget: CostBudgetGateConfig;
  physicalTelemetry: AntiDowngradeTelemetry;
  stepSaver: StepSaverMetrics;
  deltaOta: MicroDeltaOtaInfo;
  isByokActive: boolean;
}
