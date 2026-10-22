/**
/**
 * 沙箱前端实时双视口视觉自闭环验证与控制台错误零容忍自愈引擎契约定义
 */

export type DualViewportMode = 'mobile' | 'desktop' | 'side_by_side';

export interface ViewportDimension {
  name: string;
  width: number;
  height: number;
  scale: number;
  deviceLabel: string;
}

export type ConsoleLogLevel = 'error' | 'warn' | 'info';

export interface ConsoleErrorEntry {
  id: string;
  level: ConsoleLogLevel;
  message: string;
  stack?: string;
  sourceUrl?: string;
  lineNumber?: number;
  timestamp: number;
}

export interface NetworkAnomalyEntry {
  id: string;
  url: string;
  method: string;
  status: number;
  statusText: string;
  timestamp: number;
}

export interface DesignSystemAsset {
  id: string;
  name: string;
  category: 'component' | 'api' | 'token';
  importPath: string;
  description: string;
  isEnforced: boolean;
}

export type SelfHealingStatus =
  | 'idle'
  | 'harvesting_errors'
  | 'healing_prompt_injected'
  | 'recompiling'
  | 'healed_verified'
  | 'healing_exhausted';

export interface SelfHealingCycle {
  cycleId: string;
  iteration: number;
  maxIterations: number;
  status: SelfHealingStatus;
  detectedErrorsCount: number;
  lastErrorSummary?: string;
  startedAt: number;
  resolvedAt?: number;
}

export interface SandboxDualViewportState {
  activeMode: DualViewportMode;
  targetPreviewUrl: string;
  consoleErrors: ConsoleErrorEntry[];
  networkAnomalies: NetworkAnomalyEntry[];
  designAssets: DesignSystemAsset[];
  healingCycle: SelfHealingCycle;
  isLiveReloading: boolean;
}
