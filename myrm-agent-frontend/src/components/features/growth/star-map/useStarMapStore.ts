import { create } from 'zustand';
import {
  StarMapFilter,
  StarMapLink,
  StarMapNode,
  StarMapPlaybackState,
} from './starMapTypes';
import {
  INITIAL_STAR_MAP_LINKS,
  INITIAL_STAR_MAP_NODES,
} from './starMapCatalogData';
import {
  computeRadialPositions,
  getCutoffTimestamp,
} from './starMapRadialMath';

export interface StarMapState {
  nodes: StarMapNode[];
  links: StarMapLink[];
  selectedNodeId: string | null;
  hoveredNodeId: string | null;
  filter: StarMapFilter;
  playback: StarMapPlaybackState;
  isDetailSheetOpen: boolean;
  viewMode: 'map' | 'list';

  // Actions
  setFilter: (patch: Partial<StarMapFilter>) => void;
  setSelectedNodeId: (id: string | null) => void;
  setHoveredNodeId: (id: string | null) => void;
  setViewMode: (mode: 'map' | 'list') => void;
  openDetailSheet: (nodeId: string) => void;
  closeDetailSheet: () => void;
  setPlaybackProgress: (progress: number) => void;
  togglePlayback: () => void;
  setPlaybackSpeed: (speed: number) => void;
  toggleHideLabels: () => void;
  exportStarMapImage: () => Promise<boolean>;
  resetState: () => void;
}

export const useStarMapStore = create<StarMapState>((set, get) => {
  const positionedNodes = computeRadialPositions(INITIAL_STAR_MAP_NODES);

  return {
    nodes: positionedNodes,
    links: INITIAL_STAR_MAP_LINKS,
    selectedNodeId: null,
    hoveredNodeId: null,
    filter: {
      scope: 'all',
      type: 'all',
      agentScope: 'all',
      timeSpan: 'all',
      hideLabels: false,
    },
    playback: {
      isPlaying: false,
      currentProgress: 1.0,
      playbackSpeed: 1,
      currentCutoffTimestamp: Date.now(),
    },
    isDetailSheetOpen: false,
    viewMode: 'map',

    setFilter: (patch) => {
      set((state) => ({ filter: { ...state.filter, ...patch } }));
    },

    setSelectedNodeId: (id) => {
      set({ selectedNodeId: id });
    },

    setHoveredNodeId: (id) => {
      set({ hoveredNodeId: id });
    },

    setViewMode: (mode) => {
      set({ viewMode: mode });
    },

    openDetailSheet: (nodeId) => {
      set({ selectedNodeId: nodeId, isDetailSheetOpen: true });
    },

    closeDetailSheet: () => {
      set({ isDetailSheetOpen: false });
    },

    setPlaybackProgress: (progress) => {
      const clamped = Math.max(0, Math.min(1, progress));
      const cutoff = getCutoffTimestamp(get().nodes, clamped);
      set((state) => ({
        playback: {
          ...state.playback,
          currentProgress: clamped,
          currentCutoffTimestamp: cutoff,
        },
      }));
    },

    togglePlayback: () => {
      set((state) => {
        const nextPlaying = !state.playback.isPlaying;
        return {
          playback: {
            ...state.playback,
            isPlaying: nextPlaying,
          },
        };
      });
    },

    setPlaybackSpeed: (speed) => {
      set((state) => ({
        playback: {
          ...state.playback,
          playbackSpeed: speed,
        },
      }));
    },

    toggleHideLabels: () => {
      set((state) => ({
        filter: {
          ...state.filter,
          hideLabels: !state.filter.hideLabels,
        },
      }));
    },

    exportStarMapImage: async () => {
      try {
        if (typeof window !== 'undefined') {
          window.dispatchEvent(
            new CustomEvent('myrm:star-map-image-exported', {
              detail: {
                hideLabels: get().filter.hideLabels,
                timestamp: Date.now(),
              },
            })
          );
        }
        return true;
      } catch {
        return false;
      }
    },

    resetState: () => {
      const resetNodes = computeRadialPositions(INITIAL_STAR_MAP_NODES);
      set({
        nodes: resetNodes,
        links: INITIAL_STAR_MAP_LINKS,
        selectedNodeId: null,
        hoveredNodeId: null,
        filter: {
          scope: 'all',
          type: 'all',
          agentScope: 'all',
          timeSpan: 'all',
          hideLabels: false,
        },
        playback: {
          isPlaying: false,
          currentProgress: 1.0,
          playbackSpeed: 1,
          currentCutoffTimestamp: Date.now(),
        },
        isDetailSheetOpen: false,
        viewMode: 'map',
      });
    },
  };
});
