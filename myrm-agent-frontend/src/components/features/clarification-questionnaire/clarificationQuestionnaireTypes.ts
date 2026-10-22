/**
 * 交互式结构化澄清问卷卡片与防发散需求准入套件类型定义
 */

export interface QuestionOption {
  id: string;
  label: string;
  isRecommended: boolean;
  description?: string;
  nonGoalTag?: string;
}

export interface ClarificationAttachment {
  id: string;
  name: string;
  size: number;
  type: string;
  url?: string;
  uploadStatus: 'uploading' | 'ready' | 'error';
}

export interface QuestionnaireQuestion {
  id: string;
  title: string;
  description?: string;
  isMultiSelect: boolean;
  options: QuestionOption[];
  selectedOptionIds: string[];
  customTextAnswer?: string;
  attachments: ClarificationAttachment[];
}

export interface V1SpecContract {
  productShape: string;
  coreCapabilities: string[];
  nonGoals: string[];
  generatedPromptText: string;
  totalAnswered: number;
}

export type QuestionnaireStatus = 'draft' | 'synthesizing' | 'submitted' | 'cancelled';

export interface ClarificationQuestionnaireState {
  status: QuestionnaireStatus;
  questions: QuestionnaireQuestion[];
  currentQuestionIndex: number;
  isSpecModalOpen: boolean;
  activeSpecContract: V1SpecContract | null;
  lastSubmittedTime: number | null;
}
