import { create } from 'zustand';
import {
  ChunkRefinementTask,
  RefinementStatus,
  SelectionRange,
  TokenSavingsStats,
  WorkbenchTab,
} from './workbenchTypes';
import {
  applyInPlaceReplacement,
  estimateTokenSavings,
  generateSimulatedRefinement,
} from './partialRefinementEngine';

export interface WorkbenchState {
  tabs: WorkbenchTab[];
  activeTabId: string;
  isDocked: boolean;
  currentSelection: SelectionRange | null;
  refinementStatus: RefinementStatus;
  currentRefinementTask: ChunkRefinementTask | null;
  tokenStats: TokenSavingsStats;
  refinementHistory: ChunkRefinementTask[];

  // Actions
  openTab: (tab: WorkbenchTab) => void;
  closeTab: (tabId: string) => void;
  switchTab: (tabId: string) => void;
  updateTabContent: (tabId: string, content: string) => void;
  toggleDock: () => void;
  setSelection: (range: SelectionRange | null) => void;
  startRefinement: (instruction: string) => Promise<ChunkRefinementTask | null>;
  applyRefinement: () => void;
  rejectRefinement: () => void;
  resetState: () => void;
}

const INITIAL_TABS: WorkbenchTab[] = [
  {
    id: 'tab-doc-1',
    title: '行业调研深度研报.md',
    type: 'document',
    content: `# 2026 智能体算力与企业应用前瞻研报

## 核心假设与增长模型
本项目预测2026下半年智能体端侧渗透率将呈现高增长态势。
预计在金融与政企市场保持激进扩张节奏，年度ARR增长率预计超过180%。
关键驱动因素包括本地隐私沙箱成熟与微差量热更技术普及。

## 风险与应对机制
目前主要考虑供应链芯片交付周期风险。`,
    metadata: { author: 'AI Senior Analyst' },
  },
  {
    id: 'tab-browser-1',
    title: '沙箱内无头浏览器',
    type: 'browser',
    content: 'https://enterprise.internal.portal/dashboard/audit',
    metadata: { status: '200 OK' },
  },
  {
    id: 'tab-term-1',
    title: '沙箱 Bash 终端',
    type: 'terminal',
    content: '$ pnpm run build\n[vite] built in 142ms.\n$ agent-ctl status\n[OK] Daemon active.',
  },
  {
    id: 'tab-code-1',
    title: 'workflowEngine.ts',
    type: 'code',
    content: `export async function executePlanStep(stepId: string): Promise<boolean> {
  const result = await dispatchWorker(stepId);
  return result.success;
}`,
  },
];

const INITIAL_STATS: TokenSavingsStats = {
  totalRefinements: 3,
  totalTokensSaved: 14200,
  avgLatencyMs: 1800,
};

export const useWorkbenchStore = create<WorkbenchState>((set, get) => ({
  tabs: INITIAL_TABS,
  activeTabId: 'tab-doc-1',
  isDocked: true,
  currentSelection: null,
  refinementStatus: 'idle',
  currentRefinementTask: null,
  tokenStats: INITIAL_STATS,
  refinementHistory: [],

  openTab: (tab) => {
    const { tabs } = get();
    const existing = tabs.find((t) => t.id === tab.id);
    if (existing) {
      set({ activeTabId: tab.id });
      return;
    }
    set({
      tabs: [...tabs, tab],
      activeTabId: tab.id,
    });
  },

  closeTab: (tabId) => {
    const { tabs, activeTabId } = get();
    if (tabs.length <= 1) {
      return;
    }
    const filtered = tabs.filter((t) => t.id !== tabId);
    let nextActive = activeTabId;
    if (activeTabId === tabId) {
      nextActive = filtered[0].id;
    }
    set({ tabs: filtered, activeTabId: nextActive });
  },

  switchTab: (tabId) => {
    set({
      activeTabId: tabId,
      currentSelection: null,
      refinementStatus: 'idle',
      currentRefinementTask: null,
    });
  },

  updateTabContent: (tabId, content) => {
    set((state) => ({
      tabs: state.tabs.map((tab) => {
        if (tab.id === tabId) {
          return { ...tab, content, isModified: true };
        }
        return tab;
      }),
    }));
  },

  toggleDock: () => {
    set((state) => ({ isDocked: !state.isDocked }));
  },

  setSelection: (range) => {
    if (!range || !range.selectedText.trim()) {
      set({
        currentSelection: null,
        refinementStatus: 'idle',
      });
      return;
    }
    set({
      currentSelection: range,
      refinementStatus: 'prompting',
    });
  },

  startRefinement: async (instruction) => {
    const { currentSelection, activeTabId, tabs } = get();
    if (!currentSelection) {
      return null;
    }

    const activeTab = tabs.find((t) => t.id === activeTabId);
    const fullText = activeTab ? activeTab.content : '';

    set({ refinementStatus: 'refining' });

    // 模拟轻量快模型就地局部增量生成延迟 (60ms)
    await new Promise((resolve) => setTimeout(resolve, 60));

    const refinedChunk = generateSimulatedRefinement(
      currentSelection.selectedText,
      instruction
    );
    const savings = estimateTokenSavings(
      fullText.length,
      currentSelection.selectedText.length
    );

    const task: ChunkRefinementTask = {
      id: `refine-${Date.now()}`,
      tabId: activeTabId,
      range: currentSelection,
      userInstruction: instruction,
      originalChunk: currentSelection.selectedText,
      refinedChunk,
      tokenSavingsPercent: savings.savingsPercent,
      latencyMs: 1800,
      createdAt: Date.now(),
    };

    set({
      currentRefinementTask: task,
      refinementStatus: 'previewing',
    });

    return task;
  },

  applyRefinement: () => {
    const { currentRefinementTask, tabs } = get();
    if (!currentRefinementTask) {
      return;
    }

    const { tabId, range, refinedChunk } = currentRefinementTask;
    const activeTab = tabs.find((t) => t.id === tabId);
    if (!activeTab) {
      return;
    }

    const updatedContent = applyInPlaceReplacement(
      activeTab.content,
      range,
      refinedChunk
    );

    const estimatedSavings = estimateTokenSavings(
      activeTab.content.length,
      range.selectedText.length
    );

    set((state) => ({
      tabs: state.tabs.map((tab) => {
        if (tab.id === tabId) {
          return { ...tab, content: updatedContent, isModified: true };
        }
        return tab;
      }),
      refinementStatus: 'applied',
      currentSelection: null,
      currentRefinementTask: null,
      refinementHistory: [currentRefinementTask, ...state.refinementHistory],
      tokenStats: {
        totalRefinements: state.tokenStats.totalRefinements + 1,
        totalTokensSaved:
          state.tokenStats.totalTokensSaved + estimatedSavings.tokensSaved,
        avgLatencyMs: Math.round(
          (state.tokenStats.avgLatencyMs + currentRefinementTask.latencyMs) / 2
        ),
      },
    }));

    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:partial-refinement-applied', {
          detail: {
            taskId: currentRefinementTask.id,
            tabId,
            instruction: currentRefinementTask.userInstruction,
            tokensSaved: estimatedSavings.tokensSaved,
          },
        })
      );
    }
  },

  rejectRefinement: () => {
    set({
      refinementStatus: 'rejected',
      currentSelection: null,
      currentRefinementTask: null,
    });
  },

  resetState: () => {
    set({
      tabs: INITIAL_TABS,
      activeTabId: 'tab-doc-1',
      isDocked: true,
      currentSelection: null,
      refinementStatus: 'idle',
      currentRefinementTask: null,
      tokenStats: INITIAL_STATS,
      refinementHistory: [],
    });
  },
}));
