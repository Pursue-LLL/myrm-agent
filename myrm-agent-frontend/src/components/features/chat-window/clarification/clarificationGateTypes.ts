/**
 * 苏格拉底式模糊需求反向澄清门禁与无歧义 Goal Spec 类型契约
 */

export interface ClarificationOption {
  id: string;
  label: string;
  isRecommended?: boolean;
  description?: string;
}

export interface ClarificationQuestion {
  id: string;
  title: string;
  subtitle?: string;
  isMultiSelect: boolean;
  options: ClarificationOption[];
}

export type ClarificationAnswers = Record<string, string[]>;

export interface GoalSpec {
  rawPrompt: string;
  goalSummary: string;
  targetPlatform: string;
  deliverables: string[];
  constraints: string[];
  assumptionsByModel: string[];
  isSkippedByUser: boolean;
  compiledPrompt: string;
}

export type ClarificationSourceMode = 'auto' | 'command' | 'button';

export interface ClarificationGateState {
  isOpen: boolean;
  rawInput: string;
  sourceMode: ClarificationSourceMode;
  questions: ClarificationQuestion[];
  answers: ClarificationAnswers;
  customNotes: string;
  compiledSpec: GoalSpec | null;
}
