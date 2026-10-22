/**
 * [INPUT]
 * - ./revertReviewTypes::TurnFileChange, TurnRevertState, InlineReviewComment, SurgicalFixPayload
 * - @/lib/utils/apiConfig::getBackendUrl
 * - @/lib/utils/authHeaders::getAuthHeaders
 * - zustand::create
 *
 * [OUTPUT]
 * - useTurnRevertReviewStore: 会话文件撤销与 Diff 行内划词批注状态管理 Hook
 * - buildSurgicalFixPrompt: 定向修复标准化 Prompt 构造函数
 *
 * [POS]
 * 会话流文件修改一键撤销与 Diff 行内划词批注修复套件的状态机与服务集成层。
 */

import { create } from 'zustand';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import type {
  TurnFileChange,
  TurnRevertState,
  InlineReviewComment,
  SurgicalFixPayload,
} from './revertReviewTypes';

export function buildSurgicalFixPrompt(payload: SurgicalFixPayload): string {
  const lineIndicator = payload.lineNumber > 0 ? `第 ${payload.lineNumber} 行` : '局部代码';
  return [
    `[定向代码审查修复建议]`,
    `目标文件：${payload.filePath}（${lineIndicator}）`,
    `原始代码片段：`,
    '```',
    payload.selectedCode.trim() ? payload.selectedCode : '(全行上下文)',
    '```',
    `审查意见：${payload.comment}`,
    `指令要求：请根据上述行内审查意见对该文件的指定位置进行精准定向重构/修复，严格保持其余无关代码不变。`,
  ].join('\n');
}

interface RevertApiResponse {
  success: boolean;
  reverted_files?: string[];
  warnings?: string[];
  skipped_files?: string[];
}

interface TurnRevertReviewState {
  revertStates: Record<string, TurnRevertState>;
  turnChanges: Record<string, TurnFileChange[]>;
  comments: InlineReviewComment[];
  activeCommentDraft: Partial<InlineReviewComment> | null;
  activeDiffTarget: { sessionId: string; messageId: string } | null;

  setTurnChanges: (messageId: string, changes: TurnFileChange[]) => void;
  revertTurn: (sessionId: string, messageId: string) => Promise<boolean>;
  addComment: (comment: Omit<InlineReviewComment, 'id' | 'createdAt'>) => InlineReviewComment;
  removeComment: (id: string) => void;
  clearComments: () => void;
  setActiveDraft: (draft: Partial<InlineReviewComment> | null) => void;
  openDiff: (sessionId: string, messageId: string) => void;
  closeDiff: () => void;
  reset: () => void;
}

export const useTurnRevertReviewStore = create<TurnRevertReviewState>((set, get) => ({
  revertStates: {},
  turnChanges: {},
  comments: [],
  activeCommentDraft: null,
  activeDiffTarget: null,

  setTurnChanges: (messageId: string, changes: TurnFileChange[]) => {
    set((state) => ({
      turnChanges: { ...state.turnChanges, [messageId]: changes },
    }));
  },

  revertTurn: async (sessionId: string, messageId: string): Promise<boolean> => {
    set((state) => ({
      revertStates: {
        ...state.revertStates,
        [messageId]: {
          status: 'loading',
          revertedFiles: [],
          warnings: [],
          skippedFiles: [],
        },
      },
    }));

    try {
      const url = `${getBackendUrl()}/api/v1/files/revert/message`;
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          session_id: sessionId,
          message_id: messageId,
        }),
      });

      if (!res.ok) {
        throw new Error(`Revert failed with HTTP ${res.status}`);
      }

      const data: RevertApiResponse = await res.json();
      const reverted = data.reverted_files ?? [];
      const warnings = data.warnings ?? [];
      const skipped = data.skipped_files ?? [];

      set((state) => ({
        revertStates: {
          ...state.revertStates,
          [messageId]: {
            status: data.success ? 'success' : 'error',
            revertedFiles: reverted,
            warnings,
            skippedFiles: skipped,
          },
        },
      }));

      return Boolean(data.success);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Revert failed';
      set((state) => ({
        revertStates: {
          ...state.revertStates,
          [messageId]: {
            status: 'error',
            revertedFiles: [],
            warnings: [],
            skippedFiles: [],
            errorMessage: msg,
          },
        },
      }));
      return false;
    }
  },

  addComment: (commentData: Omit<InlineReviewComment, 'id' | 'createdAt'>): InlineReviewComment => {
    const newComment: InlineReviewComment = {
      ...commentData,
      id: `comment-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      createdAt: Date.now(),
    };
    set((state) => ({
      comments: [...state.comments, newComment],
      activeCommentDraft: null,
    }));
    return newComment;
  },

  removeComment: (id: string) => {
    set((state) => ({
      comments: state.comments.filter((c) => c.id !== id),
    }));
  },

  clearComments: () => {
    set({ comments: [] });
  },

  setActiveDraft: (draft: Partial<InlineReviewComment> | null) => {
    set({ activeCommentDraft: draft });
  },

  openDiff: (sessionId: string, messageId: string) => {
    set({ activeDiffTarget: { sessionId, messageId } });
  },

  closeDiff: () => {
    set({ activeDiffTarget: null, activeCommentDraft: null });
  },

  reset: () => {
    set({
      revertStates: {},
      turnChanges: {},
      comments: [],
      activeCommentDraft: null,
      activeDiffTarget: null,
    });
  },
}));
