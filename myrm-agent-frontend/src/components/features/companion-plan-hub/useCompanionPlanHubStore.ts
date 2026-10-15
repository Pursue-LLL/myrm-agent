/**
 * useCompanionPlanHubStore.ts
 * 桌面伴侣迷你计划抽屉、进度抬头显示与完工成果中枢状态管理
 */

import { create } from 'zustand';
import type {
  CompanionHubDisplayMode,
  MicroPlanDraft,
  MiniArtifactSummary,
  PlanConfirmOptions,
  TaskExecutionProgress,
} from './companionPlanHubTypes';
import { toggleSubtaskSkipState } from './companionPlanHubEngine';

export interface CompanionPlanHubStoreState {
  displayMode: CompanionHubDisplayMode;
  activePlan: MicroPlanDraft | null;
  refinedGoal: string;
  executionProgress: TaskExecutionProgress | null;
  completedArtifact: MiniArtifactSummary | null;
  isProgressLogsExpanded: boolean;

  // Actions
  setDisplayMode: (mode: CompanionHubDisplayMode) => void;
  setActivePlan: (plan: MicroPlanDraft | null) => void;
  setRefinedGoal: (goal: string) => void;
  toggleSubtaskSkip: (subtaskId: string) => void;
  confirmStartPlan: (options?: Partial<PlanConfirmOptions>) => void;
  setExecutionProgress: (
    progress: Partial<TaskExecutionProgress> | null
  ) => void;
  appendProgressLog: (log: string) => void;
  toggleProgressLogsExpanded: (expanded?: boolean) => void;
  setCompletedArtifact: (artifact: MiniArtifactSummary | null) => void;
  resetAll: () => void;
}

const mockDefaultPlan: MicroPlanDraft = {
  planId: 'plan-store-analytics',
  goal: '构建店长端经营数据看板与多端联动报表',
  targetAgentName: 'Qoder 架构工程师',
  estimatedMinutes: 8,
  createdAt: Date.now(),
  subtasks: [
    {
      id: 'st-1',
      title: '梳理店长端指标流与数据字典',
      description: '汇总客单价、坪效与当日动销率',
      status: 'pending',
      required: true,
      order: 1,
    },
    {
      id: 'st-2',
      title: '生成交互式经营图表单文件工件',
      description: '使用轻量 Canvas 呈现折线趋势图',
      status: 'pending',
      required: false,
      order: 2,
    },
    {
      id: 'st-3',
      title: '配置多端联动与自验证脚本',
      description: '运行 Python 沙盒检查异常数值边界',
      status: 'pending',
      required: false,
      order: 3,
    },
  ],
};

export const useCompanionPlanHubStore = create<CompanionPlanHubStoreState>(
  (set) => ({
    displayMode: 'plan_drawer',
    activePlan: mockDefaultPlan,
    refinedGoal: mockDefaultPlan.goal,
    executionProgress: null,
    completedArtifact: null,
    isProgressLogsExpanded: false,

    setDisplayMode: (mode: CompanionHubDisplayMode): void => {
      set({ displayMode: mode });
    },

    setActivePlan: (plan: MicroPlanDraft | null): void => {
      set({
        activePlan: plan,
        refinedGoal: plan?.goal ?? '',
        displayMode: plan !== null ? 'plan_drawer' : 'pet_only',
      });
    },

    setRefinedGoal: (goal: string): void => {
      set({ refinedGoal: goal });
    },

    toggleSubtaskSkip: (subtaskId: string): void => {
      set((state) => {
        if (state.activePlan === null) {
          return state;
        }
        const updatedSubtasks = toggleSubtaskSkipState(
          state.activePlan.subtasks,
          subtaskId
        );
        return {
          activePlan: {
            ...state.activePlan,
            subtasks: updatedSubtasks,
          },
        };
      });
    },

    confirmStartPlan: (_options?: Partial<PlanConfirmOptions>): void => {
      set((state) => {
        const plan = state.activePlan;
        const total = plan?.subtasks.length ?? 3;
        return {
          displayMode: 'progress_hud',
          executionProgress: {
            activePlanId: plan?.planId,
            currentStepIndex: 1,
            totalSteps: total,
            currentStepTitle: plan?.subtasks[0]?.title ?? '初始化任务...',
            elapsedSeconds: 0,
            logs: ['[系统] 任务已确认，伴侣正在启动后台自主执行...'],
          },
        };
      });
    },

    setExecutionProgress: (
      partial: Partial<TaskExecutionProgress> | null
    ): void => {
      set((state) => {
        if (partial === null) {
          return { executionProgress: null };
        }
        const prev = state.executionProgress ?? {
          currentStepIndex: 1,
          totalSteps: 1,
          currentStepTitle: '正在执行...',
          elapsedSeconds: 0,
          logs: [],
        };
        return {
          executionProgress: { ...prev, ...partial },
        };
      });
    },

    appendProgressLog: (log: string): void => {
      set((state) => {
        if (state.executionProgress === null) {
          return state;
        }
        return {
          executionProgress: {
            ...state.executionProgress,
            logs: [...state.executionProgress.logs, log],
          },
        };
      });
    },

    toggleProgressLogsExpanded: (expanded?: boolean): void => {
      set((state) => ({
        isProgressLogsExpanded:
          expanded !== undefined ? expanded : !state.isProgressLogsExpanded,
      }));
    },

    setCompletedArtifact: (artifact: MiniArtifactSummary | null): void => {
      set({
        completedArtifact: artifact,
        displayMode: artifact !== null ? 'artifact_bubble' : 'pet_only',
      });
    },

    resetAll: (): void => {
      set({
        displayMode: 'pet_only',
        activePlan: null,
        refinedGoal: '',
        executionProgress: null,
        completedArtifact: null,
        isProgressLogsExpanded: false,
      });
    },
  })
);
