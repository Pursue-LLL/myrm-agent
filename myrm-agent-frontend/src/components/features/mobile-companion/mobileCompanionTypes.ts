/**
 * 移动端长任务实时流式进度看板与 PWA 跨设备随行遥控套件类型定义
 */

export type TaskPhase =
  | 'initializing'
  | 'analyzing'
  | 'generating'
  | 'testing'
  | 'deploying'
  | 'completed'
  | 'paused_approval';

export interface CompanionArtifact {
  id: string;
  name: string;
  type: 'code' | 'image' | 'document' | 'bundle';
  size: number;
  downloadUrl: string;
}

export interface PendingApprovalItem {
  id: string;
  toolName: string;
  description: string;
  riskLevel: 'low' | 'medium' | 'high';
  params: Record<string, string>;
}

export interface LiveScreenshotInfo {
  id: string;
  timestamp: number;
  url: string;
  title: string;
}

export interface MobileCompanionTask {
  sessionId: string;
  taskName: string;
  phase: TaskPhase;
  progress: number;
  estimatedSecondsRemaining: number;
  startedAt: number;
  latestScreenshot?: LiveScreenshotInfo;
  pendingApproval?: PendingApprovalItem;
  artifacts: CompanionArtifact[];
  highSnrSummary: string[];
}

export interface PairingSessionConfig {
  sessionId: string;
  pairingToken: string;
  pairingUrl: string;
  expiresAt: number;
  isPwaInstallable: boolean;
}

export interface MobileCompanionState {
  isPairingModalOpen: boolean;
  pairingConfig: PairingSessionConfig | null;
  activeTask: MobileCompanionTask | null;
  isRemoteSteeringOpen: boolean;
  sentSteeringCommands: string[];
  isConnected: boolean;
}
