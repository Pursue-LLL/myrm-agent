/**
 * TemplateBot & P0 Urgency Cruise Store (Zustand)
 * 岗位模板市场与 P0 紧急高频纠偏巡航集中式状态总线
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 集中式事件广播与看门狗自动纠偏驱动。
 */

import { create } from 'zustand';
import {
  P0UrgencyCruiseState,
  TeamCloneResult,
  TemplateBotRole,
  TemplateRoleCategory,
} from './templateBotTypes';
import { getTeamRosterById } from './templateBotCatalog';
import {
  createWatchdogLogEntry,
  inspectTranscriptForDeviation,
} from './p0UrgencyWatchdogEngine';

export interface TemplateBotState {
  isMarketplaceModalOpen: boolean;
  selectedCategory: TemplateRoleCategory | 'all';
  searchKeyword: string;
  selectedBotForPreview: TemplateBotRole | null;
  instantiatedBotIds: string[];
  clonedTeamRosters: TeamCloneResult[];
  p0CruiseState: P0UrgencyCruiseState;

  // Actions
  setMarketplaceModalOpen: (open: boolean) => void;
  setSelectedCategory: (category: TemplateRoleCategory | 'all') => void;
  setSearchKeyword: (keyword: string) => void;
  setSelectedBotForPreview: (bot: TemplateBotRole | null) => void;
  instantiateBot: (botId: string) => void;
  cloneTeamRoster: (teamId: string) => TeamCloneResult | null;
  activateP0UrgencyMode: (taskId: string, taskTitle?: string) => void;
  deactivateP0UrgencyMode: () => void;
  runWatchdogInspection: (recentTurns?: readonly string[]) => void;
  tickCountdown: () => void;
  resetToDefaults: () => void;
}

const initialP0CruiseState: P0UrgencyCruiseState = {
  isActive: false,
  taskId: null,
  taskTitle: '',
  urgencyLevel: 'normal',
  inspectionIntervalSeconds: 300,
  lastInspectionTimestamp: 0,
  nextInspectionCountdownSeconds: 300,
  deviationInterceptCount: 0,
  steeringInjectedCount: 0,
  watchdogLogs: [],
};

export const useTemplateBotStore = create<TemplateBotState>((set, get) => ({
  isMarketplaceModalOpen: false,
  selectedCategory: 'all',
  searchKeyword: '',
  selectedBotForPreview: null,
  instantiatedBotIds: [],
  clonedTeamRosters: [],
  p0CruiseState: initialP0CruiseState,

  setMarketplaceModalOpen: (open: boolean) => {
    set({ isMarketplaceModalOpen: open });
  },

  setSelectedCategory: (category: TemplateRoleCategory | 'all') => {
    set({ selectedCategory: category });
  },

  setSearchKeyword: (keyword: string) => {
    set({ searchKeyword: keyword });
  },

  setSelectedBotForPreview: (bot: TemplateBotRole | null) => {
    set({ selectedBotForPreview: bot });
  },

  instantiateBot: (botId: string) => {
    set((state) => ({
      instantiatedBotIds: state.instantiatedBotIds.includes(botId)
        ? state.instantiatedBotIds
        : [...state.instantiatedBotIds, botId],
    }));
  },

  cloneTeamRoster: (teamId: string) => {
    const roster = getTeamRosterById(teamId);
    if (!roster) {
      return null;
    }

    const botIds = roster.roles.map((r) => r.id);
    const result: TeamCloneResult = {
      teamId,
      instantiatedBotIds: botIds,
      createdAtTimestamp: Date.now(),
      status: 'instantiated',
    };

    set((state) => ({
      clonedTeamRosters: [result, ...state.clonedTeamRosters],
      instantiatedBotIds: Array.from(
        new Set([...state.instantiatedBotIds, ...botIds])
      ),
    }));

    return result;
  },

  activateP0UrgencyMode: (taskId: string, taskTitle = '生产级最高优先级突发长任务') => {
    const updatedState: P0UrgencyCruiseState = {
      ...get().p0CruiseState,
      isActive: true,
      taskId,
      taskTitle,
      urgencyLevel: 'p0_urgent',
      lastInspectionTimestamp: Date.now(),
      nextInspectionCountdownSeconds: 300,
    };

    set({ p0CruiseState: updatedState });

    // 全局广播 P0 紧急模式激活事件，驱动调度器提高抢占优先级
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:p0-urgency-activated', {
          detail: { taskId, taskTitle },
        })
      );
    }
  },

  deactivateP0UrgencyMode: () => {
    set({
      p0CruiseState: {
        ...get().p0CruiseState,
        isActive: false,
        urgencyLevel: 'normal',
      },
    });
  },

  runWatchdogInspection: (recentTurns = []) => {
    const cruise = get().p0CruiseState;
    if (!cruise.isActive) {
      return;
    }

    const round = cruise.watchdogLogs.length + 1;
    const analysis = inspectTranscriptForDeviation(recentTurns);
    const logEntry = createWatchdogLogEntry(round, analysis);

    const hasSteering = analysis.status === 'steered';
    const hasDeviation = analysis.hasDeviation;

    set((state) => ({
      p0CruiseState: {
        ...state.p0CruiseState,
        lastInspectionTimestamp: Date.now(),
        nextInspectionCountdownSeconds: 300,
        deviationInterceptCount: hasDeviation
          ? state.p0CruiseState.deviationInterceptCount + 1
          : state.p0CruiseState.deviationInterceptCount,
        steeringInjectedCount: hasSteering
          ? state.p0CruiseState.steeringInjectedCount + 1
          : state.p0CruiseState.steeringInjectedCount,
        watchdogLogs: [logEntry, ...state.p0CruiseState.watchdogLogs],
      },
    }));

    // 若检测到偏离并生成了纠偏指令，广播 Steering 注入事件
    if (hasSteering && typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:p0-steering-injected', {
          detail: { logEntry },
        })
      );
    }
  },

  tickCountdown: () => {
    const current = get().p0CruiseState;
    if (!current.isActive) {
      return;
    }

    if (current.nextInspectionCountdownSeconds <= 1) {
      get().runWatchdogInspection();
    } else {
      set((state) => ({
        p0CruiseState: {
          ...state.p0CruiseState,
          nextInspectionCountdownSeconds:
            state.p0CruiseState.nextInspectionCountdownSeconds - 1,
        },
      }));
    }
  },

  resetToDefaults: () => {
    set({
      isMarketplaceModalOpen: false,
      selectedCategory: 'all',
      searchKeyword: '',
      selectedBotForPreview: null,
      instantiatedBotIds: [],
      clonedTeamRosters: [],
      p0CruiseState: initialP0CruiseState,
    });
  },
}));
