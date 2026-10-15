/**
 * companionPlanHubTypes.ts
 * 桌面伴侣全功能迷你计划抽屉、悬浮态流式需求对齐与常驻桌面任务中枢套件类型定义
 */

export type PlanSubtaskStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'skipped';

export interface PlanSubtaskItem {
  id: string;
  title: string;
  description?: string;
  status: PlanSubtaskStatus;
  required: boolean;
  order: number;
}

export interface MicroPlanDraft {
  planId: string;
  goal: string;
  targetAgentName: string;
  subtasks: PlanSubtaskItem[];
  estimatedMinutes: number;
  createdAt: number;
}

export interface TaskExecutionProgress {
  activePlanId?: string;
  currentStepIndex: number;
  totalSteps: number;
  currentStepTitle: string;
  elapsedSeconds: number;
  logs: string[];
}

export interface MiniArtifactSummary {
  artifactId: string;
  title: string;
  previewUrl?: string;
  sourcePath?: string;
  summaryText: string;
  completedAt: number;
}

export type CompanionHubDisplayMode =
  | 'pet_only'
  | 'plan_drawer'
  | 'progress_hud'
  | 'artifact_bubble';

export interface PlanConfirmOptions {
  planId: string;
  refinedGoal?: string;
  activeSubtaskIds: string[];
}
