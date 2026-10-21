import { create } from 'zustand';
import {
  CanvasLayer,
  LayerPatch,
  CanvasViewport,
  CanvasToolMode,
  BoundingBox,
  InpaintingContext,
  ZeroTokenSavingStats,
} from './infiniteCanvasTypes';
import {
  computeLassoInpaintingContext,
  calculateEstimatedSavedTokens,
} from './canvasLayerEngine';

export interface InfiniteCanvasState {
  layers: CanvasLayer[];
  selectedLayerId: string | null;
  editingTextLayerId: string | null;
  toolMode: CanvasToolMode;
  viewport: CanvasViewport;
  activeLassoBox: BoundingBox | null;
  lassoInpaintingContext: InpaintingContext | null;
  zeroTokenStats: ZeroTokenSavingStats;

  // Actions
  setToolMode: (mode: CanvasToolMode) => void;
  selectLayer: (layerId: string | null) => void;
  updateLayerPosition: (layerId: string, x: number, y: number) => void;
  startInlineTextEdit: (layerId: string) => void;
  finishInlineTextEdit: (newText: string) => void;
  cancelInlineTextEdit: () => void;
  updateLayerProperties: (layerId: string, patch: LayerPatch) => void;
  setViewport: (patch: Partial<CanvasViewport>) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  resetZoom: () => void;
  setLassoBox: (box: BoundingBox | null) => void;
  submitLassoInpainting: (prompt: string) => InpaintingContext | null;
  addLayer: (layer: CanvasLayer) => void;
  removeLayer: (layerId: string) => void;
  resetCanvas: () => void;
}

const DEFAULT_LAYERS: CanvasLayer[] = [
  {
    id: 'layer_bg_card',
    name: '主展板底色',
    type: 'container',
    x: 40,
    y: 40,
    width: 720,
    height: 480,
    opacity: 1,
    isLocked: false,
    zIndex: 1,
    backgroundColor: '#0f172a',
    borderRadius: 16,
    childLayerIds: ['layer_title', 'layer_badge', 'layer_desc'],
  },
  {
    id: 'layer_title',
    name: '主标题文本',
    type: 'text',
    x: 80,
    y: 80,
    width: 480,
    height: 56,
    opacity: 1,
    isLocked: false,
    zIndex: 2,
    text: '2026 全栈智能体生产力峰会',
    fontSize: 28,
    fontWeight: '700',
    color: '#38bdf8',
    fontFamily: 'system-ui, sans-serif',
  },
  {
    id: 'layer_badge',
    name: 'VIP 标签底色',
    type: 'shape',
    shapeType: 'pill',
    x: 580,
    y: 86,
    width: 120,
    height: 36,
    opacity: 1,
    isLocked: false,
    zIndex: 2,
    fillColor: '#0369a1',
    borderRadius: 18,
  },
  {
    id: 'layer_desc',
    name: '正文说明',
    type: 'text',
    x: 80,
    y: 160,
    width: 580,
    height: 48,
    opacity: 1,
    isLocked: false,
    zIndex: 2,
    text: '双击任意文本免 Token 直接改字，按住 Alt 框选局部区域反向重绘。',
    fontSize: 14,
    fontWeight: '400',
    color: '#94a3b8',
    fontFamily: 'system-ui, sans-serif',
  },
];

export const useInfiniteCanvasStore = create<InfiniteCanvasState>((set, get) => ({
  layers: DEFAULT_LAYERS,
  selectedLayerId: null,
  editingTextLayerId: null,
  toolMode: 'select',
  viewport: { zoom: 1, panX: 0, panY: 0 },
  activeLassoBox: null,
  lassoInpaintingContext: null,
  zeroTokenStats: {
    inlineEditCount: 0,
    estimatedSavedTokens: 0,
  },

  setToolMode: (mode: CanvasToolMode) => {
    set({ toolMode: mode });
  },

  selectLayer: (layerId: string | null) => {
    set({ selectedLayerId: layerId });
  },

  updateLayerPosition: (layerId: string, x: number, y: number) => {
    set((state) => ({
      layers: state.layers.map((l) => (l.id === layerId ? { ...l, x, y } : l)),
    }));
  },

  startInlineTextEdit: (layerId: string) => {
    const layer = get().layers.find((l) => l.id === layerId);
    if (layer && layer.type === 'text') {
      set({ editingTextLayerId: layerId, selectedLayerId: layerId });
    }
  },

  finishInlineTextEdit: (newText: string) => {
    const { editingTextLayerId, layers, zeroTokenStats } = get();
    if (!editingTextLayerId) {
      return;
    }

    const updatedLayers = layers.map((layer) => {
      if (layer.id === editingTextLayerId && layer.type === 'text') {
        return { ...layer, text: newText };
      }
      return layer;
    });

    const nextCount = zeroTokenStats.inlineEditCount + 1;
    const nextSavedTokens = calculateEstimatedSavedTokens(nextCount);

    set({
      layers: updatedLayers,
      editingTextLayerId: null,
      zeroTokenStats: {
        inlineEditCount: nextCount,
        estimatedSavedTokens: nextSavedTokens,
      },
    });
  },

  cancelInlineTextEdit: () => {
    set({ editingTextLayerId: null });
  },

  updateLayerProperties: (layerId: string, patch: LayerPatch) => {
    set((state) => ({
      layers: state.layers.map((l) => (l.id === layerId ? { ...l, ...patch } : l)),
    }));
  },

  setViewport: (patch: Partial<CanvasViewport>) => {
    set((state) => ({
      viewport: { ...state.viewport, ...patch },
    }));
  },

  zoomIn: () => {
    set((state) => ({
      viewport: { ...state.viewport, zoom: Math.min(3, Number((state.viewport.zoom + 0.1).toFixed(2))) },
    }));
  },

  zoomOut: () => {
    set((state) => ({
      viewport: { ...state.viewport, zoom: Math.max(0.3, Number((state.viewport.zoom - 0.1).toFixed(2))) },
    }));
  },

  resetZoom: () => {
    set((state) => ({
      viewport: { ...state.viewport, zoom: 1, panX: 0, panY: 0 },
    }));
  },

  setLassoBox: (box: BoundingBox | null) => {
    if (!box) {
      set({ activeLassoBox: null, lassoInpaintingContext: null });
      return;
    }

    const context = computeLassoInpaintingContext(get().layers, box);
    set({ activeLassoBox: box, lassoInpaintingContext: context });
  },

  submitLassoInpainting: (prompt: string) => {
    const { activeLassoBox, layers } = get();
    if (!activeLassoBox) {
      return null;
    }

    const context = computeLassoInpaintingContext(layers, activeLassoBox, prompt);
    set({ lassoInpaintingContext: context });

    // 触发全局反向提示注入事件，供对话框直接联动
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:canvas-inpainting-requested', { detail: context })
      );
    }
    return context;
  },

  addLayer: (layer: CanvasLayer) => {
    set((state) => ({
      layers: [...state.layers, layer],
      selectedLayerId: layer.id,
    }));
  },

  removeLayer: (layerId: string) => {
    set((state) => ({
      layers: state.layers.filter((l) => l.id !== layerId),
      selectedLayerId: state.selectedLayerId === layerId ? null : state.selectedLayerId,
    }));
  },

  resetCanvas: () => {
    set({
      layers: DEFAULT_LAYERS,
      selectedLayerId: null,
      editingTextLayerId: null,
      toolMode: 'select',
      viewport: { zoom: 1, panX: 0, panY: 0 },
      activeLassoBox: null,
      lassoInpaintingContext: null,
      zeroTokenStats: {
        inlineEditCount: 0,
        estimatedSavedTokens: 0,
      },
    });
  },
}));
