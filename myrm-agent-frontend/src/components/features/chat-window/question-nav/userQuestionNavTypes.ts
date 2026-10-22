/**
 * [INPUT]
 * - None (pure TypeScript definitions)
 *
 * [OUTPUT]
 * - UserQuestionAnchor, QuestionNavState, PendingCountCueItem
 *
 * [POS]
 * Type definitions for User Question Floating Navigator and Context Outline Jumper (Item 43 P0).
 * Strictly under 90 lines. Zero `any`.
 */

export interface UserQuestionAnchor {
  messageId: string;
  messageIndex: number;
  questionNumber: number; // 1-based index (e.g., Question 1, Question 2)
  summary: string; // Truncated prompt summary (e.g. 30-50 chars)
  fullContent: string;
  createdAt?: string | Date;
}

export interface PendingCountCueItem {
  messageId: string;
  role: string;
  snippet: string;
}

export interface QuestionNavState {
  questions: UserQuestionAnchor[];
  currentIndex: number;
  isOutlineOpen: boolean;
  pendingCount: number;
  pendingItems: PendingCountCueItem[];
}
