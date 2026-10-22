/**
 * [INPUT]
 * - ./handoffBriefTypes::HandoffBrief, HandoffItem, HandoffItemCategory, HandoffInjectPayload
 * - zustand::create
 *
 * [OUTPUT]
 * - useHandoffBriefStore: 跨会话交接简报状态机与人机审阅状态管理 Hook
 * - buildHandoffContextPrompt: 构造注入新会话的标准化 Context Prompt 函数
 *
 * [POS]
 * 跨会话交接简报后台异步流式预生成与前端可编辑审阅抽屉的状态存储与 Prompt 组装层。
 */

import { create } from 'zustand';
import type {
  HandoffBrief,
  HandoffItem,
  HandoffItemCategory,
  HandoffInjectPayload,
} from './handoffBriefTypes';

export function buildHandoffContextPrompt(brief: HandoffBrief, customNotes?: string): string {
  const selected = brief.items.filter((item) => item.enabled);
  const decisions = selected.filter((item) => item.category === 'decision');
  const todos = selected.filter((item) => item.category === 'todo');
  const constraints = selected.filter((item) => item.category === 'constraint');
  const artifacts = selected.filter((item) => item.category === 'artifact');

  const lines: string[] = [
    `[前序会话承接简报 · 已由用户可视化审阅确认]`,
    `来源会话：${brief.sessionTitle}（会话 ID: ${brief.sessionId}）`,
    `简要概括：${brief.summary}`,
  ];

  if (decisions.length > 0) {
    lines.push('\n【核心架构决策】');
    for (const d of decisions) {
      lines.push(`- ${d.content}`);
    }
  }

  if (todos.length > 0) {
    lines.push('\n【待办与下一步任务】');
    for (const t of todos) {
      lines.push(`- [ ] ${t.content}`);
    }
  }

  if (constraints.length > 0) {
    lines.push('\n【关键约束与规范】');
    for (const c of constraints) {
      lines.push(`- ⚠️ ${c.content}`);
    }
  }

  if (artifacts.length > 0) {
    lines.push('\n【关键产物与改动文件】');
    for (const a of artifacts) {
      lines.push(`- 📄 ${a.content}`);
    }
  }

  if (customNotes && customNotes.trim()) {
    lines.push('\n【用户额外补充要求】');
    lines.push(customNotes.trim());
  }

  lines.push('\n请严格基于上述经过人工审阅确认的前置事实开展本轮工作，避免重复推导与偏离既定决策。');

  return lines.join('\n');
}

interface HandoffBriefState {
  briefs: Record<string, HandoffBrief>;
  activeBriefId: string | null;
  isDrawerOpen: boolean;

  setBrief: (brief: HandoffBrief) => void;
  openDrawer: (sessionId: string) => void;
  closeDrawer: () => void;
  toggleItem: (sessionId: string, itemId: string) => void;
  toggleAllItems: (sessionId: string, enabled: boolean) => void;
  updateItemContent: (sessionId: string, itemId: string, content: string) => void;
  addItem: (sessionId: string, category: HandoffItemCategory, content: string) => void;
  removeItem: (sessionId: string, itemId: string) => void;
  buildPayload: (sessionId: string, customNotes?: string) => HandoffInjectPayload | null;
  reset: () => void;
}

export const useHandoffBriefStore = create<HandoffBriefState>((set, get) => ({
  briefs: {},
  activeBriefId: null,
  isDrawerOpen: false,

  setBrief: (brief: HandoffBrief) => {
    set((state) => ({
      briefs: { ...state.briefs, [brief.sessionId]: brief },
    }));
  },

  openDrawer: (sessionId: string) => {
    set({ activeBriefId: sessionId, isDrawerOpen: true });
  },

  closeDrawer: () => {
    set({ isDrawerOpen: false });
  },

  toggleItem: (sessionId: string, itemId: string) => {
    set((state) => {
      const brief = state.briefs[sessionId];
      if (!brief) {
        return state;
      }
      const updatedItems = brief.items.map((item) =>
        item.id === itemId ? { ...item, enabled: !item.enabled } : item
      );
      return {
        briefs: {
          ...state.briefs,
          [sessionId]: { ...brief, items: updatedItems },
        },
      };
    });
  },

  toggleAllItems: (sessionId: string, enabled: boolean) => {
    set((state) => {
      const brief = state.briefs[sessionId];
      if (!brief) {
        return state;
      }
      const updatedItems = brief.items.map((item) => ({ ...item, enabled }));
      return {
        briefs: {
          ...state.briefs,
          [sessionId]: { ...brief, items: updatedItems },
        },
      };
    });
  },

  updateItemContent: (sessionId: string, itemId: string, content: string) => {
    set((state) => {
      const brief = state.briefs[sessionId];
      if (!brief) {
        return state;
      }
      const updatedItems = brief.items.map((item) =>
        item.id === itemId ? { ...item, content } : item
      );
      return {
        briefs: {
          ...state.briefs,
          [sessionId]: { ...brief, items: updatedItems },
        },
      };
    });
  },

  addItem: (sessionId: string, category: HandoffItemCategory, content: string) => {
    set((state) => {
      const brief = state.briefs[sessionId];
      if (!brief) {
        return state;
      }
      const newItem: HandoffItem = {
        id: `custom-item-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        category,
        content: content.trim(),
        enabled: true,
        isCustom: true,
      };
      return {
        briefs: {
          ...state.briefs,
          [sessionId]: {
            ...brief,
            items: [...brief.items, newItem],
          },
        },
      };
    });
  },

  removeItem: (sessionId: string, itemId: string) => {
    set((state) => {
      const brief = state.briefs[sessionId];
      if (!brief) {
        return state;
      }
      return {
        briefs: {
          ...state.briefs,
          [sessionId]: {
            ...brief,
            items: brief.items.filter((item) => item.id !== itemId),
          },
        },
      };
    });
  },

  buildPayload: (sessionId: string, customNotes?: string): HandoffInjectPayload | null => {
    const brief = get().briefs[sessionId];
    if (!brief) {
      return null;
    }
    const selected = brief.items.filter((item) => item.enabled);
    return {
      sourceSessionId: brief.sessionId,
      sourceSessionTitle: brief.sessionTitle,
      selectedItems: selected,
      customNotes,
      injectedPrompt: buildHandoffContextPrompt(brief, customNotes),
    };
  },

  reset: () => {
    set({
      briefs: {},
      activeBriefId: null,
      isDrawerOpen: false,
    });
  },
}));
