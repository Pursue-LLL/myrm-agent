import { create } from 'zustand';
import {
  createInitialStreamState,
  DEFAULT_ARENA_MODELS,
  validateLocalProjectPath,
} from './arenaEngine';
import type {
  ArenaAdoptDecision,
  ArenaLayoutMode,
  ArenaModelConfig,
  ArenaModelStream,
  LocalProjectBinding,
} from './arenaTypes';

export interface ArenaState {
  readonly isArenaMode: boolean;
  readonly availableModels: readonly ArenaModelConfig[];
  readonly selectedModelIds: readonly string[];
  readonly layoutMode: ArenaLayoutMode;
  readonly streamMap: Record<string, ArenaModelStream>;
  readonly promptQuery: string;
  readonly localProject: LocalProjectBinding | null;
  readonly adoptedDecision: ArenaAdoptDecision | null;

  toggleArenaMode: (active?: boolean) => void;
  setSelectedModels: (modelIds: readonly string[]) => void;
  setLayoutMode: (mode: ArenaLayoutMode) => void;
  setPromptQuery: (query: string) => void;
  updateStream: (modelId: string, partial: Partial<ArenaModelStream>) => void;
  adoptSingleSolution: (modelId: string) => void;
  synthesizeSolutions: (synthesizedContent: string) => void;
  bindLocalProject: (projectPath: string, projectName: string) => boolean;
  unbindLocalProject: () => void;
  resetStreams: () => void;
  resetStore: () => void;
}

const DEFAULT_SELECTED_IDS: readonly string[] = [
  'claude-3-7-thinking',
  'deepseek-r1',
];

function initDefaultStreams(
  modelIds: readonly string[]
): Record<string, ArenaModelStream> {
  const map: Record<string, ArenaModelStream> = {};
  for (const id of modelIds) {
    map[id] = createInitialStreamState(id);
  }
  return map;
}

export const useArenaStore = create<ArenaState>((set, get) => {
  return {
    isArenaMode: false,
    availableModels: DEFAULT_ARENA_MODELS,
    selectedModelIds: DEFAULT_SELECTED_IDS,
    layoutMode: 'split_2',
    streamMap: initDefaultStreams(DEFAULT_SELECTED_IDS),
    promptQuery: '',
    localProject: null,
    adoptedDecision: null,

    toggleArenaMode: (active?: boolean) => {
      set((state) => {
        return {
          isArenaMode: active !== undefined ? active : !state.isArenaMode,
        };
      });
    },

    setSelectedModels: (modelIds: readonly string[]) => {
      const sanitized = modelIds.slice(0, 3);
      const nextLayout: ArenaLayoutMode = sanitized.length === 3 ? 'split_3' : 'split_2';
      set((state) => {
        const nextMap: Record<string, ArenaModelStream> = { ...state.streamMap };
        for (const id of sanitized) {
          if (!nextMap[id]) {
            nextMap[id] = createInitialStreamState(id);
          }
        }
        return {
          selectedModelIds: sanitized,
          layoutMode: nextLayout,
          streamMap: nextMap,
        };
      });
    },

    setLayoutMode: (mode: ArenaLayoutMode) => {
      set({ layoutMode: mode });
    },

    setPromptQuery: (query: string) => {
      set({ promptQuery: query });
    },

    updateStream: (modelId: string, partial: Partial<ArenaModelStream>) => {
      set((state) => {
        const current = state.streamMap[modelId] ?? createInitialStreamState(modelId);
        return {
          streamMap: {
            ...state.streamMap,
            [modelId]: {
              ...current,
              ...partial,
            },
          },
        };
      });
    },

    adoptSingleSolution: (modelId: string) => {
      const stream = get().streamMap[modelId];
      set({
        adoptedDecision: {
          chosenModelId: modelId,
          mode: 'adopt_single',
          synthesizedContent: stream?.contentText ?? '',
          note: `已权威采纳模型 [${modelId}] 的独立产出`,
        },
      });
    },

    synthesizeSolutions: (synthesizedContent: string) => {
      set({
        adoptedDecision: {
          chosenModelId: 'synthesized',
          mode: 'synthesize',
          synthesizedContent,
          note: '已融合各模型优势长板并生成终极方案',
        },
      });
    },

    bindLocalProject: (projectPath: string, projectName: string) => {
      const validation = validateLocalProjectPath(projectPath);
      if (!validation.isValid) {
        return false;
      }

      set({
        localProject: {
          projectPath: validation.normalizedPath,
          projectName: projectName.trim() || '本地项目',
          isBound: true,
          isOfflineAvailable: true,
          fileCount: 12,
          lastSyncTime: new Date().toISOString(),
        },
      });
      return true;
    },

    unbindLocalProject: () => {
      set({ localProject: null });
    },

    resetStreams: () => {
      const { selectedModelIds } = get();
      set({
        streamMap: initDefaultStreams(selectedModelIds),
        adoptedDecision: null,
      });
    },

    resetStore: () => {
      set({
        isArenaMode: false,
        availableModels: DEFAULT_ARENA_MODELS,
        selectedModelIds: DEFAULT_SELECTED_IDS,
        layoutMode: 'split_2',
        streamMap: initDefaultStreams(DEFAULT_SELECTED_IDS),
        promptQuery: '',
        localProject: null,
        adoptedDecision: null,
      });
    },
  };
});
