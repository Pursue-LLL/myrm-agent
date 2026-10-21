/**
 * [INPUT]
 * - UserQuestionNav.tsx
 * - UserQuestionOutlineDrawer.tsx
 * - useUserQuestionNavStore.ts
 * - userQuestionNavTypes.ts
 *
 * [OUTPUT]
 * - Facade exports for User Question Floating Navigator & Outline Jumper (Item 43 P0)
 *
 * [POS]
 * Public API of question-nav module in chat-window.
 * Strictly under 40 lines. Zero `any`.
 */

export { UserQuestionNav } from './UserQuestionNav';
export { UserQuestionOutlineDrawer } from './UserQuestionOutlineDrawer';
export { useUserQuestionNavStore } from './useUserQuestionNavStore';
export type {
  UserQuestionAnchor,
  PendingCountCueItem,
  QuestionNavState,
} from './userQuestionNavTypes';
