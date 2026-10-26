/**
 * [INPUT]
 * - Zustand create (POS: client-side workbench UI state management)
 * - FileContentResponse from @/services/workbench
 *
 * [OUTPUT]
 * - WorkbenchTabId: ('files' | 'terminal')
 * - TerminalLogEntry: Terminal execution history model
 * - useWorkbenchStore: Zustand hook managing drawer visibility, size, active tab, file selection & terminal history
 *
 * [POS]
 * Central UI store for the auxiliary workbench. File selection and terminal history belong to one chat's
 * workspace; `resetWorkspaceSession` drops them when the chat changes.
 */

import { create } from 'zustand';
import type { FileContentResponse } from '@/services/workbench';

export type WorkbenchTabId = 'files' | 'terminal';
export type WorkbenchPlacement = 'right' | 'bottom';

export interface TerminalLogEntry {
  id: string;
  command: string;
  output: string;
  exitCode: number;
  timestamp: string;
}

export interface WorkbenchState {
  isOpen: boolean;
  placement: WorkbenchPlacement;
  width: number;
  height: number;
  activeTab: WorkbenchTabId;
  selectedFilePath: string | null;
  selectedFileContent: FileContentResponse | null;
  terminalLogs: TerminalLogEntry[];

  // Actions
  toggleOpen: () => void;
  setOpen: (open: boolean) => void;
  setPlacement: (placement: WorkbenchPlacement) => void;
  setWidth: (width: number) => void;
  setHeight: (height: number) => void;
  setActiveTab: (tab: WorkbenchTabId) => void;
  setSelectedFile: (path: string | null, content?: FileContentResponse | null) => void;
  addTerminalLog: (record: { command: string; output: string; exitCode: number }) => void;
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
  selectedFilePath: null,
  selectedFileContent: null,
  terminalLogs: [],

  toggleOpen: () => set((state) => ({ isOpen: !state.isOpen })),

  setOpen: (open: boolean) => set({ isOpen: open }),

  setPlacement: (placement: WorkbenchPlacement) => set({ placement }),

  setWidth: (width: number) =>
    set({ width: Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, width)) }),

  setHeight: (height: number) =>
    set({ height: Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, height)) }),

  setActiveTab: (tab: WorkbenchTabId) => set({ activeTab: tab }),

  setSelectedFile: (path: string | null, content: FileContentResponse | null = null) =>
    set({ selectedFilePath: path, selectedFileContent: content }),

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
    set({ selectedFilePath: null, selectedFileContent: null, terminalLogs: [] }),
}));
