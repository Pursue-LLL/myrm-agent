/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/components/features/chat-window/rules-hot-reload/rulesHotReloadTypes
 * - @/components/features/chat-window/rules-hot-reload/rulesHotReloadEngine
 *
 * [OUTPUT]
 * - useWorkspaceRulesStore (POS: Central reactive store for workspace rules hot-reload)
 *
 * [POS]
 * Central reactive dispatcher for Item 199 (P1): WorkspaceRulesHotReloadAndEventBusSuite.
 * Manages active workspace rule files, automatic content-hash diffing, zero-restart cache invalidation,
 * and the global rules bypass toggle (--no-context-files).
 */

import { create } from 'zustand';
import type {
  WorkspaceRulesStoreState,
  WorkspaceRuleFile,
  RulesReloadSource,
  RuleFileDiff,
} from './rulesHotReloadTypes';
import {
  computeStringHash,
  computeCombinedHash,
  diffRuleFiles,
  formatReloadToastMessage,
  dispatchRulesReloadEvent,
} from './rulesHotReloadEngine';

export interface WorkspaceRulesStoreActions {
  readonly setRuleFiles: (
    files: readonly WorkspaceRuleFile[],
    source?: RulesReloadSource,
  ) => readonly RuleFileDiff[];
  readonly upsertRuleFile: (
    fileInput: {
      readonly path: string;
      readonly filename: string;
      readonly content: string;
    },
    source?: RulesReloadSource,
  ) => boolean;
  readonly removeRuleFile: (
    filename: string,
    source?: RulesReloadSource,
  ) => boolean;
  readonly setBypassRules: (bypass: boolean) => void;
  readonly toggleBypassRules: () => void;
  readonly reloadRules: (source?: RulesReloadSource) => Promise<readonly RuleFileDiff[]>;
  readonly dismissNotification: () => void;
  readonly resetStore: () => void;
}

export type WorkspaceRulesStore = WorkspaceRulesStoreState & WorkspaceRulesStoreActions;

const initialState: WorkspaceRulesStoreState = {
  ruleFiles: [],
  combinedHash: '00000000',
  bypassRules: false,
  isReloading: false,
  lastReloadedAt: null,
  lastReloadSource: null,
  notificationMessage: null,
};

export const useWorkspaceRulesStore = create<WorkspaceRulesStore>((set, get) => ({
  ...initialState,

  setRuleFiles: (files: readonly WorkspaceRuleFile[], source = 'file_watcher') => {
    const prevFiles = get().ruleFiles;
    const diffs = diffRuleFiles(prevFiles, files);
    const newCombinedHash = computeCombinedHash(files);
    const message = formatReloadToastMessage(diffs, source);

    dispatchRulesReloadEvent({
      source,
      diffs,
      combinedHash: newCombinedHash,
      timestamp: Date.now(),
    });

    set({
      ruleFiles: files,
      combinedHash: newCombinedHash,
      lastReloadedAt: Date.now(),
      lastReloadSource: source,
      notificationMessage: message,
    });

    return diffs;
  },

  upsertRuleFile: (fileInput, source = 'file_watcher') => {
    const { path, filename, content } = fileInput;
    const hash = computeStringHash(content);
    const updatedFile: WorkspaceRuleFile = {
      path,
      filename,
      content,
      hash,
      lastModified: Date.now(),
      sizeBytes: content.length,
    };

    const currentFiles = get().ruleFiles;
    const existingIndex = currentFiles.findIndex(
      (f) => f.filename.toLowerCase() === filename.toLowerCase(),
    );

    let nextFiles: WorkspaceRuleFile[];
    if (existingIndex >= 0) {
      nextFiles = currentFiles.map((f, i) => (i === existingIndex ? updatedFile : f));
    } else {
      nextFiles = [...currentFiles, updatedFile];
    }

    get().setRuleFiles(nextFiles, source);
    return true;
  },

  removeRuleFile: (filename, source = 'file_watcher') => {
    const currentFiles = get().ruleFiles;
    const nextFiles = currentFiles.filter(
      (f) => f.filename.toLowerCase() !== filename.toLowerCase(),
    );

    if (nextFiles.length === currentFiles.length) {
      return false;
    }

    get().setRuleFiles(nextFiles, source);
    return true;
  },

  setBypassRules: (bypass: boolean) => {
    set({ bypassRules: bypass });
  },

  toggleBypassRules: () => {
    set((state) => ({ bypassRules: !state.bypassRules }));
  },

  reloadRules: async (source = 'manual_reload') => {
    set({ isReloading: true });

    // 模拟轻量毫秒级校验
    await new Promise((resolve) => setTimeout(resolve, 50));

    const currentFiles = get().ruleFiles;
    const diffs = get().setRuleFiles(currentFiles, source);

    set({ isReloading: false });
    return diffs;
  },

  dismissNotification: () => {
    set({ notificationMessage: null });
  },

  resetStore: () => {
    set({ ...initialState });
  },
}));
