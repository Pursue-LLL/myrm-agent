/**
 * [INPUT]
 * - swarmTypes: SwarmModeConfig, SwarmSubagentTask, RecalledRuleItem, OwnerRiskItem
 *
 * [OUTPUT]
 * - useSwarmExecutionStore: Zustand store managing swarm mode, recalled rules HUD & owner risks
 *
 * [POS]
 * Client state management for Swarm Coordination, Memory Recall HUD & Owner Risk Checklist (Item 42 P0).
 * Strictly under 240 lines. Zero `any`.
 */

import { create } from "zustand";
import type {
  OwnerRiskItem,
  RecalledRuleItem,
  SwarmSubagentTask,
} from "./swarmTypes";

interface SwarmExecutionState {
  isSwarmEnabled: boolean;
  concurrencyQuota: number;
  subagentTasks: SwarmSubagentTask[];
  recalledRules: RecalledRuleItem[];
  activeRulesPrompt: string;
  ownerRisks: OwnerRiskItem[];
  isRulesDrawerOpen: boolean;
  isTasksDrawerOpen: boolean;
  isLoading: boolean;

  setSwarmEnabled: (enabled: boolean) => void;
  setConcurrencyQuota: (quota: number) => void;
  setRulesDrawerOpen: (open: boolean) => void;
  setTasksDrawerOpen: (open: boolean) => void;
  fetchSwarmConfig: (chatId: string) => Promise<void>;
  toggleSwarm: (chatId: string) => Promise<boolean>;
  fetchSubagentTasks: (chatId: string) => Promise<void>;
  fetchRecalledRules: (chatId: string) => Promise<void>;
  toggleRuleActive: (chatId: string, ruleId: string, isActive: boolean) => Promise<boolean>;
  fetchOwnerRisks: (chatId: string) => Promise<void>;
  toggleRiskConfirm: (
    chatId: string,
    riskId: string,
    isConfirmed: boolean,
    confirmedBy?: string
  ) => Promise<boolean>;
  reset: () => void;
}

export const useSwarmExecutionStore = create<SwarmExecutionState>((set, get) => ({
  isSwarmEnabled: false,
  concurrencyQuota: 5,
  subagentTasks: [],
  recalledRules: [],
  activeRulesPrompt: "",
  ownerRisks: [],
  isRulesDrawerOpen: false,
  isTasksDrawerOpen: false,
  isLoading: false,

  setSwarmEnabled: (enabled: boolean) => {
    set({ isSwarmEnabled: enabled });
  },

  setConcurrencyQuota: (quota: number) => {
    set({ concurrencyQuota: Math.max(1, Math.min(10, quota)) });
  },

  setRulesDrawerOpen: (open: boolean) => {
    set({ isRulesDrawerOpen: open });
  },

  setTasksDrawerOpen: (open: boolean) => {
    set({ isTasksDrawerOpen: open });
  },

  fetchSwarmConfig: async (chatId: string): Promise<void> => {
    if (!chatId) {
      return;
    }
    try {
      const response = await fetch(`/api/v1/chats/${chatId}/swarm/config`);
      if (!response.ok) {
        return;
      }
      const json = (await response.json()) as {
        data?: { enabled: boolean; concurrency_quota: number };
      };
      if (json.data) {
        set({
          isSwarmEnabled: json.data.enabled,
          concurrencyQuota: json.data.concurrency_quota,
        });
      }
    } catch {
      // Ignore network errors in poll
    }
  },

  toggleSwarm: async (chatId: string): Promise<boolean> => {
    const nextState = !get().isSwarmEnabled;
    set({ isSwarmEnabled: nextState });
    if (!chatId) {
      return true;
    }

    try {
      const response = await fetch(`/api/v1/chats/${chatId}/swarm/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: nextState,
          concurrency_quota: get().concurrencyQuota,
        }),
      });
      return response.ok;
    } catch {
      return false;
    }
  },

  fetchSubagentTasks: async (chatId: string): Promise<void> => {
    if (!chatId) {
      return;
    }
    try {
      const response = await fetch(`/api/v1/chats/${chatId}/swarm/tasks`);
      if (!response.ok) {
        return;
      }
      const json = (await response.json()) as {
        data?: Array<{
          task_id: string;
          role_title: string;
          boundary_description: string;
          status: "pending" | "running" | "completed" | "failed";
          current_step?: string;
          assigned_tools?: string[];
        }>;
      };
      if (json.data) {
        const mapped: SwarmSubagentTask[] = json.data.map((t) => ({
          taskId: t.task_id,
          roleTitle: t.role_title,
          boundaryDescription: t.boundary_description,
          status: t.status,
          currentStep: t.current_step,
          assignedTools: t.assigned_tools,
        }));
        set({ subagentTasks: mapped });
      }
    } catch {
      // Ignore network error
    }
  },

  fetchRecalledRules: async (chatId: string): Promise<void> => {
    if (!chatId) {
      return;
    }
    try {
      const response = await fetch(`/api/v1/chats/${chatId}/swarm/recalled-rules`);
      if (!response.ok) {
        return;
      }
      const json = (await response.json()) as {
        data?: {
          rules: Array<{
            rule_id: string;
            summary: string;
            source_turn_id: string;
            confidence: number;
            is_active: boolean;
            category: string;
          }>;
          active_prompt: string;
        };
      };
      if (json.data) {
        const mapped: RecalledRuleItem[] = json.data.rules.map((r) => ({
          ruleId: r.rule_id,
          summary: r.summary,
          sourceTurnId: r.source_turn_id,
          confidence: r.confidence,
          isActive: r.is_active,
          category: r.category,
        }));
        set({
          recalledRules: mapped,
          activeRulesPrompt: json.data.active_prompt,
        });
      }
    } catch {
      // Ignore network error
    }
  },

  toggleRuleActive: async (
    chatId: string,
    ruleId: string,
    isActive: boolean
  ): Promise<boolean> => {
    // Optimistic update
    set((state) => ({
      recalledRules: state.recalledRules.map((r) =>
        r.ruleId === ruleId ? { ...r, isActive } : r
      ),
    }));

    if (!chatId) {
      return true;
    }
    try {
      const response = await fetch(
        `/api/v1/chats/${chatId}/swarm/recalled-rules/${ruleId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_active: isActive }),
        }
      );
      return response.ok;
    } catch {
      return false;
    }
  },

  fetchOwnerRisks: async (chatId: string): Promise<void> => {
    if (!chatId) {
      return;
    }
    try {
      const response = await fetch(`/api/v1/chats/${chatId}/swarm/risks`);
      if (!response.ok) {
        return;
      }
      const json = (await response.json()) as {
        data?: Array<{
          risk_id: string;
          title: string;
          description: string;
          severity: "low" | "medium" | "high" | "critical";
          is_confirmed: boolean;
          confirmed_by?: string;
          external_constraint_type: string;
          remediation_hint?: string;
        }>;
      };
      if (json.data) {
        const mapped: OwnerRiskItem[] = json.data.map((item) => ({
          riskId: item.risk_id,
          title: item.title,
          description: item.description,
          severity: item.severity,
          isConfirmed: item.is_confirmed,
          confirmedBy: item.confirmed_by,
          externalConstraintType: item.external_constraint_type,
          remediationHint: item.remediation_hint,
        }));
        set({ ownerRisks: mapped });
      }
    } catch {
      // Ignore network error
    }
  },

  toggleRiskConfirm: async (
    chatId: string,
    riskId: string,
    isConfirmed: boolean,
    confirmedBy = "store_owner"
  ): Promise<boolean> => {
    // Optimistic update
    set((state) => ({
      ownerRisks: state.ownerRisks.map((item) =>
        item.riskId === riskId
          ? { ...item, isConfirmed, confirmedBy: isConfirmed ? confirmedBy : "" }
          : item
      ),
    }));

    if (!chatId) {
      return true;
    }
    try {
      const response = await fetch(`/api/v1/chats/${chatId}/swarm/risks/${riskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          is_confirmed: isConfirmed,
          confirmed_by: isConfirmed ? confirmedBy : "",
        }),
      });
      return response.ok;
    } catch {
      return false;
    }
  },

  reset: () => {
    set({
      isSwarmEnabled: false,
      subagentTasks: [],
      recalledRules: [],
      activeRulesPrompt: "",
      ownerRisks: [],
      isRulesDrawerOpen: false,
      isTasksDrawerOpen: false,
      isLoading: false,
    });
  },
}));
