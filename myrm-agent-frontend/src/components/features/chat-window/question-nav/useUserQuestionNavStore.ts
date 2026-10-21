/**
 * [INPUT]
 * - userQuestionNavTypes: UserQuestionAnchor, PendingCountCueItem
 *
 * [OUTPUT]
 * - useUserQuestionNavStore: Zustand store managing user question anchors, outline drawer, and pending cues
 *
 * [POS]
 * State management for User Question Floating Navigator & Outline Jumper (Item 43 P0).
 * Strictly under 200 lines. Zero `any`.
 */

import { create } from "zustand";
import type { PendingCountCueItem, UserQuestionAnchor } from "./userQuestionNavTypes";

interface RawMessageLike {
  messageId?: string | number;
  role?: string;
  content?: string;
  createdAt?: string | Date;
}

interface UserQuestionNavStoreState {
  questions: UserQuestionAnchor[];
  currentIndex: number;
  isOutlineOpen: boolean;
  pendingCount: number;
  pendingItems: PendingCountCueItem[];

  syncMessages: (messages: RawMessageLike[], lastVisibleIndex?: number) => void;
  setCurrentIndex: (index: number) => void;
  setOutlineOpen: (open: boolean) => void;
  getPreviousQuestion: () => UserQuestionAnchor | null;
  getNextQuestion: () => UserQuestionAnchor | null;
  reset: () => void;
}

export const useUserQuestionNavStore = create<UserQuestionNavStoreState>((set, get) => ({
  questions: [],
  currentIndex: 0,
  isOutlineOpen: false,
  pendingCount: 0,
  pendingItems: [],

  syncMessages: (messages: RawMessageLike[], lastVisibleIndex = -1) => {
    if (!messages || messages.length === 0) {
      set({ questions: [], currentIndex: 0, pendingCount: 0, pendingItems: [] });
      return;
    }

    const anchors: UserQuestionAnchor[] = [];
    let questionCounter = 1;

    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      if (msg.role === "user" && msg.content) {
        const cleanContent = msg.content.trim();
        const summary =
          cleanContent.length > 40
            ? `${cleanContent.slice(0, 40)}...`
            : cleanContent;

        anchors.push({
          messageId: String(msg.messageId ?? `msg_${i}`),
          messageIndex: i,
          questionNumber: questionCounter++,
          summary,
          fullContent: cleanContent,
          createdAt: msg.createdAt,
        });
      }
    }

    // Calculate pending items below visible viewport if specified
    let pendingCount = 0;
    const pendingItems: PendingCountCueItem[] = [];

    if (lastVisibleIndex >= 0 && lastVisibleIndex < messages.length - 1) {
      const remainingMessages = messages.slice(lastVisibleIndex + 1);
      pendingCount = remainingMessages.length;
      for (const item of remainingMessages.slice(0, 3)) {
        if (item.content) {
          const firstLine = item.content.split("\n")[0].trim();
          pendingItems.push({
            messageId: String(item.messageId ?? ""),
            role: item.role ?? "assistant",
            snippet: firstLine.length > 28 ? `${firstLine.slice(0, 28)}...` : firstLine,
          });
        }
      }
    }

    set((state) => {
      const clampedIndex = Math.min(
        Math.max(0, state.currentIndex),
        Math.max(0, anchors.length - 1)
      );
      return {
        questions: anchors,
        currentIndex: clampedIndex,
        pendingCount,
        pendingItems,
      };
    });
  },

  setCurrentIndex: (index: number) => {
    const { questions } = get();
    if (questions.length === 0) {
      set({ currentIndex: 0 });
      return;
    }
    const clamped = Math.max(0, Math.min(questions.length - 1, index));
    set({ currentIndex: clamped });
  },

  setOutlineOpen: (open: boolean) => {
    set({ isOutlineOpen: open });
  },

  getPreviousQuestion: () => {
    const { questions, currentIndex } = get();
    if (questions.length === 0 || currentIndex <= 0) {
      return null;
    }
    return questions[currentIndex - 1];
  },

  getNextQuestion: () => {
    const { questions, currentIndex } = get();
    if (questions.length === 0 || currentIndex >= questions.length - 1) {
      return null;
    }
    return questions[currentIndex + 1];
  },

  reset: () => {
    set({
      questions: [],
      currentIndex: 0,
      isOutlineOpen: false,
      pendingCount: 0,
      pendingItems: [],
    });
  },
}));
