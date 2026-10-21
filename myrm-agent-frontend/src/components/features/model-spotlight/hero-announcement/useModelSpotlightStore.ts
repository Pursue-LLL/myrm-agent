import { create } from 'zustand';
import {
  DismissRecord,
  PlaygroundMessage,
  SpotlightModelItem,
} from './modelSpotlightTypes';
import {
  filterAvailableSpotlights,
  SPOTLIGHT_CATALOG,
} from './spotlightCatalogData';

export interface ModelSpotlightState {
  catalog: SpotlightModelItem[];
  activeSpotlightId: string | null;
  dismissedRecords: Record<string, DismissRecord>;
  isBannerCollapsed: boolean;
  isPlaygroundOpen: boolean;
  isMountModalOpen: boolean;
  playgroundSpotlight: SpotlightModelItem | null;
  playgroundMessages: PlaygroundMessage[];
  isPlaygroundThinking: boolean;
  currentAgentModelId: string;
  mountTargetSpotlight: SpotlightModelItem | null;
  lastMountedModelId: string | null;

  // Actions
  setActiveSpotlight: (id: string | null) => void;
  toggleBannerCollapsed: () => void;
  dismissSpotlight: (id: string, permanent: boolean) => void;
  restoreDismissedSpotlights: () => void;
  openPlayground: (spotlight: SpotlightModelItem) => void;
  closePlayground: () => void;
  sendPlaygroundPrompt: (prompt: string) => Promise<void>;
  clearPlayground: () => void;
  openMountModal: (spotlight: SpotlightModelItem) => void;
  closeMountModal: () => void;
  confirmMountModel: (targetSpotlight: SpotlightModelItem) => void;
  setCurrentAgentModelId: (modelId: string) => void;
}

export const useModelSpotlightStore = create<ModelSpotlightState>((set, get) => ({
  catalog: SPOTLIGHT_CATALOG,
  activeSpotlightId: SPOTLIGHT_CATALOG[0]?.id || null,
  dismissedRecords: {},
  isBannerCollapsed: false,
  isPlaygroundOpen: false,
  isMountModalOpen: false,
  playgroundSpotlight: null,
  playgroundMessages: [],
  isPlaygroundThinking: false,
  currentAgentModelId: 'openai/gpt-4o',
  mountTargetSpotlight: null,
  lastMountedModelId: null,

  setActiveSpotlight: (id: string | null) => {
    set({ activeSpotlightId: id });
  },

  toggleBannerCollapsed: () => {
    set((state) => ({ isBannerCollapsed: !state.isBannerCollapsed }));
  },

  dismissSpotlight: (id: string, permanent: boolean) => {
    const record: DismissRecord = {
      spotlightId: id,
      dismissedAt: Date.now(),
      permanent,
    };
    const nextDismissed = { ...get().dismissedRecords, [id]: record };
    const available = filterAvailableSpotlights(get().catalog, nextDismissed);
    const nextActiveId = available.length > 0 ? available[0].id : null;

    set({
      dismissedRecords: nextDismissed,
      activeSpotlightId: nextActiveId,
    });
  },

  restoreDismissedSpotlights: () => {
    set({
      dismissedRecords: {},
      activeSpotlightId: get().catalog[0]?.id || null,
      isBannerCollapsed: false,
    });
  },

  openPlayground: (spotlight: SpotlightModelItem) => {
    set({
      isPlaygroundOpen: true,
      playgroundSpotlight: spotlight,
      playgroundMessages: [
        {
          id: `msg-sys-${Date.now()}`,
          role: 'assistant',
          content: `欢迎来到 ${spotlight.name} 极速试用沙箱！支持原生 ${spotlight.contextWindow.toLocaleString()} 超长上下文，已加载基准测试参数。您可以直接在下方输入问题或点击预设 Prompt 测试生成质量。`,
          timestamp: Date.now(),
          latencyMs: 45,
        },
      ],
    });
  },

  closePlayground: () => {
    set({
      isPlaygroundOpen: false,
      playgroundSpotlight: null,
      isPlaygroundThinking: false,
    });
  },

  clearPlayground: () => {
    set({ playgroundMessages: [] });
  },

  sendPlaygroundPrompt: async (prompt: string) => {
    if (!prompt.trim()) {
      return;
    }
    const userMsg: PlaygroundMessage = {
      id: `msg-user-${Date.now()}`,
      role: 'user',
      content: prompt.trim(),
      timestamp: Date.now(),
    };

    set((state) => ({
      playgroundMessages: [...state.playgroundMessages, userMsg],
      isPlaygroundThinking: true,
    }));

    const spotlight = get().playgroundSpotlight;
    const modelName = spotlight ? spotlight.name : '前沿大模型';

    // 模拟前沿大模型的亚秒级快速思考与回复
    await new Promise((resolve) => setTimeout(resolve, 80));

    const simulatedReply =
      `【${modelName} 实时输出】\n` +
      `根据您提出的问题 "${prompt.slice(0, 30)}..."，在深度推理与上下文基准测试下：\n` +
      `1. 架构逻辑：已采用最高效的非阻塞管线与原子操作，避免级联锁竞争；\n` +
      `2. 性能评估：首字延迟 ~180ms，上下文吞吐稳定在 85+ Tokens/s；\n` +
      `3. 验证建议：可直接将此模型挂载至当前智能体，投入复杂长任务执行。`;

    const assistantMsg: PlaygroundMessage = {
      id: `msg-asst-${Date.now()}`,
      role: 'assistant',
      content: simulatedReply,
      timestamp: Date.now(),
      latencyMs: 185,
    };

    set((state) => ({
      playgroundMessages: [...state.playgroundMessages, assistantMsg],
      isPlaygroundThinking: false,
    }));
  },

  openMountModal: (spotlight: SpotlightModelItem) => {
    set({
      isMountModalOpen: true,
      mountTargetSpotlight: spotlight,
    });
  },

  closeMountModal: () => {
    set({
      isMountModalOpen: false,
      mountTargetSpotlight: null,
    });
  },

  confirmMountModel: (targetSpotlight: SpotlightModelItem) => {
    set({
      currentAgentModelId: targetSpotlight.modelId,
      lastMountedModelId: targetSpotlight.modelId,
      isMountModalOpen: false,
      mountTargetSpotlight: null,
    });

    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:model-hot-mounted', {
          detail: {
            modelId: targetSpotlight.modelId,
            name: targetSpotlight.name,
            contextWindow: targetSpotlight.contextWindow,
            timestamp: Date.now(),
          },
        })
      );
    }
  },

  setCurrentAgentModelId: (modelId: string) => {
    set({ currentAgentModelId: modelId });
  },
}));
