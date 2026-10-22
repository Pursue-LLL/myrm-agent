/**
 * [INPUT]
 * - None (pure TypeScript type definitions)
 *
 * [OUTPUT]
 * - QuestionType, QuestionOption, StructuredQuestionPayload, StructuredQuestionResponse, StructuredQuestionCardProps
 *
 * [POS]
 * Type definitions for Structured Asking Card with Skip Control (Item 47 P0).
 * Strictly under 80 lines. Zero `any`.
 */

export type QuestionType =
  | 'single_choice'
  | 'multi_choice'
  | 'boolean_confirm'
  | 'text_slot';

export interface QuestionOption {
  id: string;
  label: string;
  description?: string;
  isRecommended?: boolean;
  isDefault?: boolean;
}

export interface StructuredQuestionResponse {
  selectedOptionIds: string[];
  textValue?: string;
  isSkipped: boolean;
  answeredAt: number;
}

export interface StructuredQuestionPayload {
  questionId: string;
  question: string;
  questionType: QuestionType;
  context?: string;
  options: QuestionOption[];
  allowSkip?: boolean;
  defaultOptionId?: string;
  status: 'pending' | 'answered' | 'skipped';
  response?: StructuredQuestionResponse;
}

export interface StructuredQuestionCardProps {
  payload: StructuredQuestionPayload;
  onSubmitResponse?: (response: StructuredQuestionResponse) => void;
  onSkip?: () => void;
  className?: string;
  enableKeyboardShortcuts?: boolean;
}
