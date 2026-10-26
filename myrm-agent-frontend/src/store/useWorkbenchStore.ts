/**
 * [INPUT]
 * - Zustand create (POS: client-side workbench UI state management)
 *
 * [OUTPUT]
 * - WorkbenchTabId: ('files' | 'terminal')
 * - TerminalLogEntry: Terminal execution history model
 * - useWorkbenchStore: Zustand hook managing drawer visibility, size, active tab & terminal history
 *
 * [POS]
 * Central UI store for the auxiliary workbench. Terminal history belongs to one chat's workspace;
 * `resetWorkspaceSession` drops it when the chat changes and advances `sessionEpoch`, so a reply still in
 * flight for the previous chat can tell it is stale and not write into the new session.
 */

import { create } from 'zustand';

export type WorkbenchTabId = 'files' | 'terminal';
export type WorkbenchPlacement = 'right' | 'bottom';

export interface TerminalLogEntry {
  id: string;
  command: string;
  output: string;
  /** Null when the command never finished (refused, timed out, or the request failed). */
  exitCode: number | null;
  timestamp: string;
}

export interface WorkbenchState {
  isOpen: boolean;
  placement: WorkbenchPlacement;
  width: number;
  height: number;
  activeTab: WorkbenchTabId;
  terminalLogs: TerminalLogEntry[];
  sessionEpoch: number;

  // Actions
  toggleOpen: () => void;
  setOpen: (open: boolean) => void;
  setPlacement: (placement: WorkbenchPlacement) => void;
  setWidth: (width: number) => void;
  setHeight: (height: number) => void;
  setActiveTab: (tab: WorkbenchTabId) => void;
  addTerminalLog: (record: { command: string; output: string; exitCode: number | null }) => void;
  clearTerminalLogs: () => void;
  resetWorkspaceSession: () => void;
}

const DEFAULT_WIDTH = 480;
const DEFAULT_HEIGHT = 320;
const MIN_WIDTH = 320;
const MAX_WIDTH = 960;
const MIN_HEIGHT = 200;
const MAX_HEIGHT = 640;

export const useWorkbenchStore = create<WorkbenchState>((set) => ({
  isOpen: false,
  placement: 'right',
  width: DEFAULT_WIDTH,
  height: DEFAULT_HEIGHT,
  activeTab: 'files',
  terminalLogs: [],
  sessionEpoch: 0,

  toggleOpen: () => set((state) => ({ isOpen: !state.isOpen })),

  setOpen: (open: boolean) => set({ isOpen: open }),

  setPlacement: (placement: WorkbenchPlacement) => set({ placement }),

  setWidth: (width: number) =>
    set({ width: Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, width)) }),

  setHeight: (height: number) =>
    set({ height: Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, height)) }),

  setActiveTab: (tab: WorkbenchTabId) => set({ activeTab: tab }),

  addTerminalLog: ({ command, output, exitCode }) =>
    set((state) => {
      const entry: TerminalLogEntry = {
        id: `term-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        command,
        output,
        exitCode,
        timestamp: new Date().toISOString(),
      };
      // Keep last 100 commands
      const updated = [...state.terminalLogs, entry].slice(-100);
      return { terminalLogs: updated };
    }),

  clearTerminalLogs: () => set({ terminalLogs: [] }),

  resetWorkspaceSession: () =>
    set((state) => ({
      terminalLogs: [],
      sessionEpoch: state.sessionEpoch + 1,
    })),
}));
