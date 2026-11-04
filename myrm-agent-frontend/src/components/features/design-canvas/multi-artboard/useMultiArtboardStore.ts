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
import { DEFAULT_THEME_LOCK, INITIAL_ARTBOARDS } from './multiArtboardSeed';

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
