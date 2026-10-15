'use client';

export type ThinkingBudgetLevel = 'off' | 'low' | 'medium' | 'high';

export interface ThinkingBudgetOption {
  level: ThinkingBudgetLevel;
  label: string;
  tokenLimit: number;
  estSeconds: string;
  description: string;
}

export type ReasoningStageStatus = 'in-progress' | 'completed';

export interface ReasoningStage {
  id: string;
  stepNumber: number;
  title: string;
  summary: string;
  rawContent: string;
  durationSec: number;
  status: ReasoningStageStatus;
}

export interface ReasoningTimelineState {
  isThinking: boolean;
  isExpanded: boolean;
  totalElapsedSec: number;
  thinkingTokens: number;
  stages: ReasoningStage[];
  rawContent: string;
}
