/**
 * 交互式引导漫游与极简开箱核对清单类型定义
 * 严禁 any 类型，确保严格 Type Hints 与只读保障
 */

export type SpotlightPlacement = 'top' | 'bottom' | 'left' | 'right' | 'center';

export interface TourStep {
  readonly id: string;
  readonly title: string;
  readonly description: string;
  readonly targetSelector?: string;
  readonly placement: SpotlightPlacement;
  readonly actionLabel?: string;
  readonly badgeText?: string;
}

export interface ChecklistItem {
  readonly id: string;
  readonly title: string;
  readonly description: string;
  readonly actionUrl?: string;
  readonly completed: boolean;
  readonly required: boolean;
}

export interface PlaygroundTemplate {
  readonly id: string;
  readonly title: string;
  readonly description: string;
  readonly category: string;
  readonly prompt: string;
  readonly tags: readonly string[];
  readonly estimatedSeconds: number;
}

export interface SpotlightRect {
  readonly top: number;
  readonly left: number;
  readonly width: number;
  readonly height: number;
}

export interface ChecklistProgress {
  readonly completedCount: number;
  readonly totalCount: number;
  readonly percentage: number;
  readonly isAllCompleted: boolean;
}

export interface SandboxExecutionPayload {
  readonly prompt: string;
  readonly tags: readonly string[];
  readonly initialParams: Record<string, string>;
  readonly templateId: string;
}
