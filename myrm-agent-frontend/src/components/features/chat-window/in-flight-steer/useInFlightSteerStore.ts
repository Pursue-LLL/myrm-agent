/**
 * [INPUT] ActiveSubagentSwimlane, Steer instruction, Cancel calls
 * [OUTPUT] useInFlightSteerStore (Zustand state store for subagent swimlanes & steer commands)
 * [POS] Features -> Chat Window -> In-Flight Steer -> Store
 */

import { create } from 'zustand';
import { steerBackgroundTask, cancelBackgroundTask } from '@/services/background-tasks';
import { showI18nToast } from '@/services/i18nToastService';
import { toast } from '@/lib/utils/toast';
import type {
  ActiveSubagentSwimlane,
  CollapsibleLongTaskSummary,
  InFlightSteerState,
  SubagentRunStatus,
} from './inFlightSteerTypes';

/** The server's own reason when it gave one, else the translated fallback. */
const reportFailure = (error: unknown, fallbackKey: string) => {
  if (error instanceof Error && error.message) {
    toast.error(error.message);
    return;
  }
  showI18nToast(fallbackKey, undefined, { type: 'error' });
};

export const useInFlightSteerStore = create<InFlightSteerState>()((set, get) => ({
  swimlanes: [],
  activePopoverSubagentId: null,
  taskSummaries: {},
  isSteering: false,

  registerSwimlane: (swimlane: ActiveSubagentSwimlane) => {
    set((state) => {
      const existingIndex = state.swimlanes.findIndex((s) => s.id === swimlane.id);
      if (existingIndex >= 0) {
        const updated = [...state.swimlanes];
        updated[existingIndex] = { ...updated[existingIndex], ...swimlane };
        return { swimlanes: updated };
      }
      return { swimlanes: [...state.swimlanes, swimlane] };
    });
  },

  updateSwimlaneStatus: (id: string, status: SubagentRunStatus, currentStep?: string, tokensUsed?: number) => {
    set((state) => ({
      swimlanes: state.swimlanes.map((s) => {
        if (s.id === id) {
          return {
            ...s,
            status,
            currentStep: currentStep ?? s.currentStep,
            tokensUsed: tokensUsed ?? s.tokensUsed,
          };
        }
        return s;
      }),
    }));
  },

  removeSwimlane: (id: string) => {
    set((state) => ({
      swimlanes: state.swimlanes.filter((s) => s.id !== id),
      activePopoverSubagentId: state.activePopoverSubagentId === id ? null : state.activePopoverSubagentId,
    }));
  },

  openSteerPopover: (subagentId: string) => {
    set({ activePopoverSubagentId: subagentId });
  },

  closeSteerPopover: () => {
    set({ activePopoverSubagentId: null });
  },

  sendSteerInstruction: async (subagentId: string, instruction: string): Promise<boolean> => {
    const trimmed = instruction.trim();
    if (!trimmed) {
      return false;
    }

    const swimlane = get().swimlanes.find((s) => s.id === subagentId);
    if (!swimlane) {
      showI18nToast('chat.inFlightSteer.subagentNotFound', undefined, { type: 'error' });
      return false;
    }

    set({ isSteering: true });
    try {
      if (swimlane.taskId) {
        await steerBackgroundTask(swimlane.taskId, trimmed);
      }

      const now = Date.now();
      set((state) => ({
        swimlanes: state.swimlanes.map((s) => {
          if (s.id === subagentId) {
            return {
              ...s,
              lastInstruction: trimmed,
              lastSteeredAt: now,
              currentStep: `已注入纠偏: ${trimmed.slice(0, 24)}...`,
            };
          }
          return s;
        }),
        activePopoverSubagentId: null,
      }));

      showI18nToast('chat.inFlightSteer.steerSent', { name: swimlane.name }, { type: 'success' });
      return true;
    } catch (error) {
      reportFailure(error, 'chat.inFlightSteer.steerFailed');
      return false;
    } finally {
      set({ isSteering: false });
    }
  },

  stopAndKeepArtifacts: async (subagentId: string): Promise<boolean> => {
    const swimlane = get().swimlanes.find((s) => s.id === subagentId);
    if (!swimlane) {
      showI18nToast('chat.inFlightSteer.subagentNotFound', undefined, { type: 'error' });
      return false;
    }

    set({ isSteering: true });
    try {
      if (swimlane.taskId) {
        await cancelBackgroundTask(swimlane.taskId);
      }

      const now = Date.now();
      set((state) => ({
        swimlanes: state.swimlanes.map((s) => {
          if (s.id === subagentId) {
            return {
              ...s,
              status: 'stopped',
              currentStep: '已提前叫停 (保留半成品草稿)',
              partialDeliverable: s.partialDeliverable ?? {
                title: `${s.name} 半成品产物`,
                summary: `在执行阶段【${s.currentStep}】提前叫停，已保留已有分析结论与部分代码草案。`,
                capturedAt: now,
              },
            };
          }
          return s;
        }),
        activePopoverSubagentId: null,
      }));

      showI18nToast('chat.inFlightSteer.stopped', { name: swimlane.name }, { type: 'success' });
      return true;
    } catch (error) {
      reportFailure(error, 'chat.inFlightSteer.stopFailed');
      return false;
    } finally {
      set({ isSteering: false });
    }
  },

  setTaskSummary: (summary: CollapsibleLongTaskSummary) => {
    set((state) => ({
      taskSummaries: {
        ...state.taskSummaries,
        [summary.id]: summary,
      },
    }));
  },

  toggleSummaryCollapse: (summaryId: string) => {
    set((state) => {
      const existing = state.taskSummaries[summaryId];
      if (!existing) {
        return state;
      }
      return {
        taskSummaries: {
          ...state.taskSummaries,
          [summaryId]: {
            ...existing,
            isCollapsed: !existing.isCollapsed,
          },
        },
      };
    });
  },

  clearSwimlanes: () => {
    set({
      swimlanes: [],
      activePopoverSubagentId: null,
      taskSummaries: {},
    });
  },
}));
