/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/components/features/chat-window/cli-passthrough/cliPassthroughTypes
 * - @/components/features/chat-window/cli-passthrough/cliPassthroughEngine
 *
 * [OUTPUT]
 * - useCliPassthroughStore (POS: Central reactive store for CLI pass-through executions)
 *
 * [POS]
 * Central reactive dispatcher for Item 194 (P0).
 * Orchestrates CLI command parsing, safety guard gating, output collection,
 * and context-visibility switching between '!cmd' and '!!cmd'.
 */

import { create } from 'zustand';
import type {
  CliCommandRecord,
  CliPassthroughStoreState,
} from './cliPassthroughTypes';
import {
  parseCliPassThroughInput,
  auditCliCommand,
} from './cliPassthroughEngine';

export interface CliExecutionResult {
  readonly output: string;
  readonly exitCode: number;
}

export type CliCustomExecutor = (command: string) => Promise<CliExecutionResult>;

export interface CliPassthroughStoreActions {
  readonly executeCommand: (
    rawInput: string,
    executor?: CliCustomExecutor,
  ) => Promise<CliCommandRecord | null>;
  readonly toggleDrawer: (open?: boolean) => void;
  readonly selectCommand: (id: string) => void;
  readonly clearHistory: () => void;
  readonly resetStore: () => void;
}

export type CliPassthroughStore = CliPassthroughStoreState & CliPassthroughStoreActions;

const initialState: CliPassthroughStoreState = {
  history: [],
  activeCommand: null,
  isDrawerOpen: false,
  isExecuting: false,
};

export const useCliPassthroughStore = create<CliPassthroughStore>((set, get) => ({
  ...initialState,

  executeCommand: async (rawInput: string, executor?: CliCustomExecutor) => {
    const parsed = parseCliPassThroughInput(rawInput);
    if (!parsed.isCliCommand || !parsed.command || !parsed.mode) {
      return null;
    }

    const commandId = `cli_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const startTime = Date.now();

    // 1. 安全守卫审计
    const audit = auditCliCommand(parsed.command);
    if (!audit.allowed) {
      const blockedRecord: CliCommandRecord = {
        id: commandId,
        rawInput,
        command: parsed.command,
        mode: parsed.mode,
        status: 'blocked_by_guard',
        output: audit.reason ?? '指令已被安全策略拦截',
        exitCode: 126,
        durationMs: 0,
        timestamp: startTime,
        guardReason: audit.reason,
      };

      set((state) => ({
        history: [blockedRecord, ...state.history],
        activeCommand: blockedRecord,
        isDrawerOpen: true,
        isExecuting: false,
      }));

      return blockedRecord;
    }

    // 2. 正常初始化并进入 running 状态
    const runningRecord: CliCommandRecord = {
      id: commandId,
      rawInput,
      command: parsed.command,
      mode: parsed.mode,
      status: 'running',
      output: '',
      exitCode: null,
      durationMs: 0,
      timestamp: startTime,
    };

    set((state) => ({
      history: [runningRecord, ...state.history],
      activeCommand: runningRecord,
      isDrawerOpen: true,
      isExecuting: true,
    }));

    try {
      let result: CliExecutionResult;
      if (executor) {
        result = await executor(parsed.command);
      } else {
        // 默认模拟本地沙箱极速响应
        await new Promise((resolve) => setTimeout(resolve, 80));
        result = {
          output: `[local-exec] Command executed successfully: ${parsed.command}`,
          exitCode: 0,
        };
      }

      const durationMs = Date.now() - startTime;
      const completedRecord: CliCommandRecord = {
        ...runningRecord,
        status: result.exitCode === 0 ? 'success' : 'failed',
        output: result.output,
        exitCode: result.exitCode,
        durationMs,
      };

      set((state) => ({
        history: state.history.map((item) => (item.id === commandId ? completedRecord : item)),
        activeCommand: completedRecord,
        isExecuting: false,
      }));

      return completedRecord;
    } catch (err: unknown) {
      const durationMs = Date.now() - startTime;
      const errorMessage = err instanceof Error ? err.message : String(err);
      const failedRecord: CliCommandRecord = {
        ...runningRecord,
        status: 'failed',
        output: `执行异常: ${errorMessage}`,
        exitCode: 1,
        durationMs,
      };

      set((state) => ({
        history: state.history.map((item) => (item.id === commandId ? failedRecord : item)),
        activeCommand: failedRecord,
        isExecuting: false,
      }));

      return failedRecord;
    }
  },

  toggleDrawer: (open?: boolean) => {
    set((state) => ({
      isDrawerOpen: typeof open === 'boolean' ? open : !state.isDrawerOpen,
    }));
  },

  selectCommand: (id: string) => {
    const item = get().history.find((h) => h.id === id);
    if (item) {
      set({ activeCommand: item });
    }
  },

  clearHistory: () => {
    set({
      history: [],
      activeCommand: null,
      isDrawerOpen: false,
    });
  },

  resetStore: () => {
    set({ ...initialState });
  },
}));
