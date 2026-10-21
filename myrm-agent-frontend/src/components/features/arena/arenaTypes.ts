/**
 * 多模型分栏对照竞技场与本地项目工作区类型定义
 * 严禁 any 类型，确保严格 Type Hints 与只读保障
 */

export type ArenaStreamStatus = 'idle' | 'streaming' | 'completed' | 'error';

export type ArenaLayoutMode = 'split_2' | 'split_3' | 'tabs';

export interface ArenaModelConfig {
  readonly id: string;
  readonly name: string;
  readonly provider: string;
  readonly tier: 'turbo' | 'pro' | 'reasoning';
  readonly contextWindow: string;
  readonly badgeColor: string;
}

export interface ArenaModelStream {
  readonly modelId: string;
  readonly status: ArenaStreamStatus;
  readonly reasoningText?: string;
  readonly contentText: string;
  readonly latencyMs: number;
  readonly tokenCount: number;
  readonly error?: string;
}

export interface ArenaAdoptDecision {
  readonly chosenModelId: string;
  readonly mode: 'adopt_single' | 'synthesize';
  readonly synthesizedContent?: string;
  readonly note?: string;
}

export interface LocalProjectBinding {
  readonly projectPath: string;
  readonly projectName: string;
  readonly isBound: boolean;
  readonly isOfflineAvailable: boolean;
  readonly fileCount: number;
  readonly lastSyncTime: string;
}
