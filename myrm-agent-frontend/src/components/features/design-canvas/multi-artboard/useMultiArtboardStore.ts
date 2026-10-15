'use client';

import { create } from 'zustand';
import {
  Artboard,
  ArtboardFlowLink,
  CanvasViewportTransform,
  DeviceFrameType,
  PrototypePlaybackState,
  ThemeLockConfig,
} from './multiArtboardTypes';
import {
  applyThemeLockToArtboards,
  calculateArtboardGridLayout,
  extractAllFlowLinksFromArtboards,
} from './artboardLayoutEngine';

export interface MultiArtboardState {
  artboards: Artboard[];
  selectedArtboardId: string | null;
  selectedLayerId: string | null;
  flowLinks: ArtboardFlowLink[];
  showFlowLinks: boolean;
  themeLock: ThemeLockConfig;
  playbackState: PrototypePlaybackState;
  viewport: CanvasViewportTransform;

  // 画板操作
  selectArtboard: (id: string | null) => void;
  selectLayer: (artboardId: string, layerId: string | null) => void;
  setArtboards: (artboards: Artboard[]) => void;
  arrangeArtboardsGrid: (columns?: number) => void;
  updateArtboardPosition: (id: string, x: number, y: number) => void;
  
  // 风格锁
  updateThemeLock: (partial: Partial<ThemeLockConfig>) => void;
  toggleThemeLock: (locked?: boolean) => void;
  
  // 连线展示
  toggleFlowLinks: (show?: boolean) => void;
  addFlowLink: (link: ArtboardFlowLink) => void;
  removeFlowLink: (linkId: string) => void;

  // 视口平移缩放
  setViewportPan: (panX: number, panY: number) => void;
  setViewportZoom: (zoom: number) => void;
  resetViewport: () => void;

  // 原型免 Token 播放演示
  startPlayback: (initialArtboardId?: string) => void;
  stopPlayback: () => void;
  navigatePlayback: (targetArtboardId: string, transition?: 'slide' | 'fade' | 'instant') => void;
  goBackPlayback: () => void;
  setPlaybackDeviceFrame: (frame: DeviceFrameType) => void;
  togglePlaybackHotspotHints: (show?: boolean) => void;
}

const DEFAULT_THEME_LOCK: ThemeLockConfig = {
  isLocked: true,
  presetName: 'Neo-Clean Indigo',
  primaryColor: '#6366f1',
  secondaryColor: '#4f46e5',
  backgroundColor: '#0f172a',
  borderRadius: 16,
  fontFamily: 'Inter, system-ui, sans-serif',
};

const INITIAL_ARTBOARDS: Artboard[] = [
  {
    id: 'artboard-home',
    title: '01 · 工作台首页',
    width: 320,
    height: 568,
    x: 60,
    y: 80,
    layers: [
      {
        id: 'bg-1',
        name: '背景底板',
        type: 'container',
        x: 0,
        y: 0,
        width: 320,
        height: 568,
        zIndex: 0,
        opacity: 1,
        backgroundColor: '#0f172a',
        borderRadius: 16,
      },
      {
        id: 'title-1',
        name: '页面标题',
        type: 'text',
        x: 24,
        y: 40,
        width: 200,
        height: 32,
        zIndex: 1,
        opacity: 1,
        text: '我的工作台',
        fontSize: 22,
        fontWeight: 'bold',
        color: '#f8fafc',
      },
      {
        id: 'btn-goto-schedule',
        name: '查看今日日程按钮',
        type: 'button',
        x: 24,
        y: 100,
        width: 272,
        height: 48,
        zIndex: 2,
        opacity: 1,
        text: '查看今日日程 ➔',
        fontSize: 14,
        fontWeight: '600',
        color: '#ffffff',
        backgroundColor: '#6366f1',
        borderRadius: 16,
        targetArtboardId: 'artboard-schedule',
        interactionTooltip: '点击跳转至日程表',
      },
      {
        id: 'btn-goto-todo',
        name: '代办事项清单按钮',
        type: 'button',
        x: 24,
        y: 168,
        width: 272,
        height: 48,
        zIndex: 2,
        opacity: 1,
        text: '待办任务清单 (4) ➔',
        fontSize: 14,
        fontWeight: '600',
        color: '#ffffff',
        backgroundColor: '#6366f1',
        borderRadius: 16,
        targetArtboardId: 'artboard-todo',
        interactionTooltip: '点击跳转至待办页',
      },
      {
        id: 'btn-goto-profile',
        name: '进入设置',
        type: 'button',
        x: 24,
        y: 480,
        width: 272,
        height: 42,
        zIndex: 2,
        opacity: 0.9,
        text: '偏好设置 ➔',
        fontSize: 13,
        fontWeight: '500',
        color: '#cbd5e1',
        backgroundColor: '#1e293b',
        borderRadius: 12,
        targetArtboardId: 'artboard-settings',
        interactionTooltip: '点击跳转至设置',
      },
    ],
  },
  {
    id: 'artboard-schedule',
    title: '02 · 日程排期表',
    width: 320,
    height: 568,
    x: 460,
    y: 80,
    layers: [
      {
        id: 'bg-2',
        name: '背景底板',
        type: 'container',
        x: 0,
        y: 0,
        width: 320,
        height: 568,
        zIndex: 0,
        opacity: 1,
        backgroundColor: '#0f172a',
        borderRadius: 16,
      },
      {
        id: 'title-2',
        name: '页面标题',
        type: 'text',
        x: 24,
        y: 40,
        width: 200,
        height: 32,
        zIndex: 1,
        opacity: 1,
        text: '今日排期日程',
        fontSize: 22,
        fontWeight: 'bold',
        color: '#f8fafc',
      },
      {
        id: 'btn-back-home-from-schedule',
        name: '返回首页按钮',
        type: 'button',
        x: 24,
        y: 480,
        width: 272,
        height: 44,
        zIndex: 2,
        opacity: 1,
        text: '⬅ 返回工作台',
        fontSize: 14,
        fontWeight: '600',
        color: '#ffffff',
        backgroundColor: '#6366f1',
        borderRadius: 16,
        targetArtboardId: 'artboard-home',
        interactionTooltip: '点击返回首页',
      },
    ],
  },
  {
    id: 'artboard-todo',
    title: '03 · 待办清单页',
    width: 320,
    height: 568,
    x: 860,
    y: 80,
    layers: [
      {
        id: 'bg-3',
        name: '背景底板',
        type: 'container',
        x: 0,
        y: 0,
        width: 320,
        height: 568,
        zIndex: 0,
        opacity: 1,
        backgroundColor: '#0f172a',
        borderRadius: 16,
      },
      {
        id: 'title-3',
        name: '页面标题',
        type: 'text',
        x: 24,
        y: 40,
        width: 200,
        height: 32,
        zIndex: 1,
        opacity: 1,
        text: '待办任务清单',
        fontSize: 22,
        fontWeight: 'bold',
        color: '#f8fafc',
      },
      {
        id: 'btn-back-home-from-todo',
        name: '返回首页按钮',
        type: 'button',
        x: 24,
        y: 480,
        width: 272,
        height: 44,
        zIndex: 2,
        opacity: 1,
        text: '⬅ 返回工作台',
        fontSize: 14,
        fontWeight: '600',
        color: '#ffffff',
        backgroundColor: '#6366f1',
        borderRadius: 16,
        targetArtboardId: 'artboard-home',
        interactionTooltip: '点击返回首页',
      },
    ],
  },
  {
    id: 'artboard-settings',
    title: '04 · 偏好设置页',
    width: 320,
    height: 568,
    x: 1260,
    y: 80,
    layers: [
      {
        id: 'bg-4',
        name: '背景底板',
        type: 'container',
        x: 0,
        y: 0,
        width: 320,
        height: 568,
        zIndex: 0,
        opacity: 1,
        backgroundColor: '#0f172a',
        borderRadius: 16,
      },
      {
        id: 'title-4',
        name: '页面标题',
        type: 'text',
        x: 24,
        y: 40,
        width: 200,
        height: 32,
        zIndex: 1,
        opacity: 1,
        text: '系统偏好设置',
        fontSize: 22,
        fontWeight: 'bold',
        color: '#f8fafc',
      },
      {
        id: 'btn-back-home-from-settings',
        name: '返回首页按钮',
        type: 'button',
        x: 24,
        y: 480,
        width: 272,
        height: 44,
        zIndex: 2,
        opacity: 1,
        text: '⬅ 返回工作台',
        fontSize: 14,
        fontWeight: '600',
        color: '#ffffff',
        backgroundColor: '#6366f1',
        borderRadius: 16,
        targetArtboardId: 'artboard-home',
        interactionTooltip: '点击返回首页',
      },
    ],
  },
];

export const useMultiArtboardStore = create<MultiArtboardState>((set, get) => ({
  artboards: INITIAL_ARTBOARDS,
  selectedArtboardId: 'artboard-home',
  selectedLayerId: null,
  flowLinks: extractAllFlowLinksFromArtboards(INITIAL_ARTBOARDS),
  showFlowLinks: true,
  themeLock: DEFAULT_THEME_LOCK,
  playbackState: {
    isPlaying: false,
    currentArtboardId: 'artboard-home',
    historyStack: [],
    deviceFrame: 'iphone',
    showHotspotHints: true,
    activeTransition: 'slide',
  },
  viewport: {
    panX: 40,
    panY: 30,
    zoom: 0.85,
  },

  selectArtboard: (id: string | null) => {
    set({ selectedArtboardId: id, selectedLayerId: null });
  },

  selectLayer: (artboardId: string, layerId: string | null) => {
    set({ selectedArtboardId: artboardId, selectedLayerId: layerId });
  },

  setArtboards: (artboards: Artboard[]) => {
    const { themeLock } = get();
    const lockedArtboards = applyThemeLockToArtboards(artboards, themeLock);
    const flowLinks = extractAllFlowLinksFromArtboards(lockedArtboards);
    set({ artboards: lockedArtboards, flowLinks });
  },

  arrangeArtboardsGrid: (columns: number = 4) => {
    const { artboards } = get();
    const arranged = calculateArtboardGridLayout(artboards, columns);
    set({ artboards: arranged });
  },

  updateArtboardPosition: (id: string, x: number, y: number) => {
    set((state) => ({
      artboards: state.artboards.map((ab) => (ab.id === id ? { ...ab, x, y } : ab)),
    }));
  },

  updateThemeLock: (partial: Partial<ThemeLockConfig>) => {
    set((state) => {
      const nextTheme = { ...state.themeLock, ...partial };
      const nextArtboards = applyThemeLockToArtboards(state.artboards, nextTheme);
      return {
        themeLock: nextTheme,
        artboards: nextArtboards,
      };
    });
  },

  toggleThemeLock: (locked?: boolean) => {
    set((state) => {
      const isLocked = locked !== undefined ? locked : !state.themeLock.isLocked;
      const nextTheme = { ...state.themeLock, isLocked };
      const nextArtboards = applyThemeLockToArtboards(state.artboards, nextTheme);
      return {
        themeLock: nextTheme,
        artboards: nextArtboards,
      };
    });
  },

  toggleFlowLinks: (show?: boolean) => {
    set((state) => ({
      showFlowLinks: show !== undefined ? show : !state.showFlowLinks,
    }));
  },

  addFlowLink: (link: ArtboardFlowLink) => {
    set((state) => ({
      flowLinks: [...state.flowLinks.filter((l) => l.id !== link.id), link],
    }));
  },

  removeFlowLink: (linkId: string) => {
    set((state) => ({
      flowLinks: state.flowLinks.filter((l) => l.id !== linkId),
    }));
  },

  setViewportPan: (panX: number, panY: number) => {
    set((state) => ({
      viewport: { ...state.viewport, panX, panY },
    }));
  },

  setViewportZoom: (zoom: number) => {
    const safeZoom = Math.min(2.5, Math.max(0.2, zoom));
    set((state) => ({
      viewport: { ...state.viewport, zoom: safeZoom },
    }));
  },

  resetViewport: () => {
    set({ viewport: { panX: 40, panY: 30, zoom: 0.85 } });
  },

  startPlayback: (initialArtboardId?: string) => {
    const { artboards, selectedArtboardId } = get();
    const startId = initialArtboardId || selectedArtboardId || (artboards[0]?.id ?? null);
    set({
      playbackState: {
        isPlaying: true,
        currentArtboardId: startId,
        historyStack: [],
        deviceFrame: 'iphone',
        showHotspotHints: true,
        activeTransition: 'instant',
      },
    });
  },

  stopPlayback: () => {
    set((state) => ({
      playbackState: { ...state.playbackState, isPlaying: false },
    }));
  },

  navigatePlayback: (targetArtboardId: string, transition: 'slide' | 'fade' | 'instant' = 'slide') => {
    const { playbackState } = get();
    if (!playbackState.currentArtboardId) {
      return;
    }
    set({
      playbackState: {
        ...playbackState,
        currentArtboardId: targetArtboardId,
        historyStack: [...playbackState.historyStack, playbackState.currentArtboardId],
        activeTransition: transition,
      },
    });
  },

  goBackPlayback: () => {
    const { playbackState } = get();
    if (playbackState.historyStack.length === 0) {
      return;
    }
    const nextHistory = [...playbackState.historyStack];
    const previousArtboardId = nextHistory.pop();
    if (previousArtboardId) {
      set({
        playbackState: {
          ...playbackState,
          currentArtboardId: previousArtboardId,
          historyStack: nextHistory,
          activeTransition: 'slide',
        },
      });
    }
  },

  setPlaybackDeviceFrame: (frame: DeviceFrameType) => {
    set((state) => ({
      playbackState: { ...state.playbackState, deviceFrame: frame },
    }));
  },

  togglePlaybackHotspotHints: (show?: boolean) => {
    set((state) => ({
      playbackState: {
        ...state.playbackState,
        showHotspotHints:
          show !== undefined ? show : !state.playbackState.showHotspotHints,
      },
    }));
  },
}));
