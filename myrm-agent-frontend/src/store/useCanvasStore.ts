/**
 * [INPUT]
 * - zustand (POS: 状态管理)
 * - @/services/canvas (POS: Canvas API)
 *
 * [OUTPUT]
 * - useCanvasStore: Canvas 列表与活跃画布状态管理
 *
 * [POS] 管理画布列表的 CRUD 状态及活跃画布的选择。
 */

import { create } from 'zustand';

import {
  type CanvasItem,
  createCanvas as apiCreateCanvas,
  deleteCanvas as apiDeleteCanvas,
  listCanvases,
  updateCanvas as apiUpdateCanvas,
} from '@/services/canvas';

interface CanvasState {
  canvases: CanvasItem[];
  loading: boolean;
  activeCanvasId: string | null;

  fetchCanvases: () => Promise<void>;
  createCanvas: (name?: string, agentId?: string, chatId?: string) => Promise<CanvasItem>;
  renameCanvas: (id: string, name: string) => Promise<void>;
  removeCanvas: (id: string) => Promise<void>;
  setActiveCanvas: (id: string | null) => void;
}

export const useCanvasStore = create<CanvasState>((set, get) => ({
  canvases: [],
  loading: false,
  activeCanvasId: null,

  fetchCanvases: async () => {
    set({ loading: true });
    try {
      const canvases = await listCanvases();
      set({ canvases });
    } finally {
      set({ loading: false });
    }
  },

  createCanvas: async (name, agentId, chatId) => {
    const canvas = await apiCreateCanvas(name, agentId, chatId);
    set((s) => ({ canvases: [canvas, ...s.canvases] }));
    return canvas;
  },

  renameCanvas: async (id, name) => {
    await apiUpdateCanvas(id, { name });
    set((s) => ({
      canvases: s.canvases.map((c) => (c.id === id ? { ...c, name } : c)),
    }));
  },

  removeCanvas: async (id) => {
    await apiDeleteCanvas(id);
    const { activeCanvasId } = get();
    set((s) => ({
      canvases: s.canvases.filter((c) => c.id !== id),
      activeCanvasId: activeCanvasId === id ? null : activeCanvasId,
    }));
  },

  setActiveCanvas: (id) => set({ activeCanvasId: id }),
}));
