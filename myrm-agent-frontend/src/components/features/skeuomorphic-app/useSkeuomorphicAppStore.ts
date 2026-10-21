import { create } from 'zustand';
import {
  ArtifactPlayItem,
  SkeuomorphicSkinType,
} from './skeuomorphicTypes';
import {
  getDefaultMockArtifacts,
  wrapArtifactIndex,
} from './skeuomorphicAppEngine';
import { skeuomorphicAudioEngine } from './skeuomorphicAudioEngine';

interface SkeuomorphicAppState {
  activeSkin: SkeuomorphicSkinType;
  artifacts: ArtifactPlayItem[];
  activeItemIndex: number;
  isDetailOpen: boolean;
  soundEnabled: boolean;
  hapticEnabled: boolean;
  volume: number;
  autoPlay: boolean;
  isMinimized: boolean;

  setActiveSkin: (skin: SkeuomorphicSkinType) => void;
  setArtifacts: (items: ArtifactPlayItem[]) => void;
  nextItem: () => void;
  prevItem: () => void;
  selectItemIndex: (index: number) => void;
  openDetailModal: () => void;
  closeDetailModal: () => void;
  toggleSound: () => void;
  toggleHaptic: () => void;
  setVolume: (vol: number) => void;
  toggleAutoPlay: () => void;
  toggleMinimized: () => void;
  resetStore: () => void;
}

export const useSkeuomorphicAppStore = create<SkeuomorphicAppState>((set, get) => ({
  activeSkin: 'classic_ipod',
  artifacts: getDefaultMockArtifacts(),
  activeItemIndex: 0,
  isDetailOpen: false,
  soundEnabled: true,
  hapticEnabled: true,
  volume: 0.35,
  autoPlay: false,
  isMinimized: false,

  setActiveSkin: (skin) => {
    skeuomorphicAudioEngine.playLcdConfirmBeep();
    set({ activeSkin: skin });
  },

  setArtifacts: (items) => {
    set({
      artifacts: items,
      activeItemIndex: 0,
    });
  },

  nextItem: () => {
    const { artifacts, activeItemIndex } = get();
    if (artifacts.length === 0) {
      return;
    }
    skeuomorphicAudioEngine.playRatchetClick();
    const nextIdx = wrapArtifactIndex(activeItemIndex + 1, artifacts.length);
    set({ activeItemIndex: nextIdx });
  },

  prevItem: () => {
    const { artifacts, activeItemIndex } = get();
    if (artifacts.length === 0) {
      return;
    }
    skeuomorphicAudioEngine.playRatchetClick();
    const prevIdx = wrapArtifactIndex(activeItemIndex - 1, artifacts.length);
    set({ activeItemIndex: prevIdx });
  },

  selectItemIndex: (index) => {
    const { artifacts } = get();
    if (artifacts.length === 0) {
      return;
    }
    skeuomorphicAudioEngine.playRatchetClick();
    set({ activeItemIndex: wrapArtifactIndex(index, artifacts.length) });
  },

  openDetailModal: () => {
    skeuomorphicAudioEngine.playLcdConfirmBeep();
    set({ isDetailOpen: true });
  },

  closeDetailModal: () => {
    skeuomorphicAudioEngine.playRatchetClick();
    set({ isDetailOpen: false });
  },

  toggleSound: () => {
    const nextVal = !get().soundEnabled;
    skeuomorphicAudioEngine.updateConfig({ soundEnabled: nextVal });
    set({ soundEnabled: nextVal });
  },

  toggleHaptic: () => {
    const nextVal = !get().hapticEnabled;
    skeuomorphicAudioEngine.updateConfig({ hapticEnabled: nextVal });
    set({ hapticEnabled: nextVal });
  },

  setVolume: (vol) => {
    const clamped = Math.max(0, Math.min(1, vol));
    skeuomorphicAudioEngine.updateConfig({ volume: clamped });
    set({ volume: clamped });
  },

  toggleAutoPlay: () => {
    const nextVal = !get().autoPlay;
    skeuomorphicAudioEngine.playLcdConfirmBeep();
    set({ autoPlay: nextVal });
  },

  toggleMinimized: () => {
    skeuomorphicAudioEngine.playRatchetClick();
    set((state) => ({ isMinimized: !state.isMinimized }));
  },

  resetStore: () => {
    set({
      activeSkin: 'classic_ipod',
      artifacts: getDefaultMockArtifacts(),
      activeItemIndex: 0,
      isDetailOpen: false,
      soundEnabled: true,
      hapticEnabled: true,
      volume: 0.35,
      autoPlay: false,
      isMinimized: false,
    });
  },
}));
