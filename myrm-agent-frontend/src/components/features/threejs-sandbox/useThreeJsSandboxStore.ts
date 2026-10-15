import { create } from 'zustand';
import {
  SandboxCameraMode,
  SandboxViewportMode,
  WebGLPerformanceMetrics,
  WebGLLogEntry,
} from './threeJsTypes';

interface ThreeJsSandboxState {
  sceneId: string;
  sceneTitle: string;
  sceneCode: string;
  viewportMode: SandboxViewportMode;
  cameraMode: SandboxCameraMode;
  metrics: WebGLPerformanceMetrics;
  logs: WebGLLogEntry[];
  isConsoleOpen: boolean;
  isStatsOpen: boolean;
  cameraResetCount: number;

  setScene: (id: string, title: string, code: string) => void;
  setViewportMode: (mode: SandboxViewportMode) => void;
  setCameraMode: (mode: SandboxCameraMode) => void;
  updateMetrics: (metrics: Partial<WebGLPerformanceMetrics>) => void;
  addLog: (entry: Omit<WebGLLogEntry, 'id'>) => void;
  clearLogs: () => void;
  toggleConsole: () => void;
  toggleStats: () => void;
  triggerCameraReset: () => void;
}

const defaultMetrics: WebGLPerformanceMetrics = {
  fps: 60,
  drawCalls: 1,
  triangles: 0,
  geometries: 0,
  textures: 0,
};

export const useThreeJsSandboxStore = create<ThreeJsSandboxState>((set) => ({
  sceneId: 'scene-default',
  sceneTitle: '3D 场景沙箱',
  sceneCode: '',
  viewportMode: 'inline',
  cameraMode: 'orbit',
  metrics: defaultMetrics,
  logs: [],
  isConsoleOpen: false,
  isStatsOpen: true,
  cameraResetCount: 0,

  setScene: (id, title, code) =>
    set({
      sceneId: id,
      sceneTitle: title,
      sceneCode: code,
      logs: [],
      metrics: defaultMetrics,
    }),

  setViewportMode: (viewportMode) => set({ viewportMode }),

  setCameraMode: (cameraMode) => set({ cameraMode }),

  updateMetrics: (partial) =>
    set((state) => ({
      metrics: { ...state.metrics, ...partial },
    })),

  addLog: (entry) =>
    set((state) => {
      const newEntry: WebGLLogEntry = {
        ...entry,
        id: `log-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      };
      // 保留最近 100 条日志，避免无限膨胀
      const updated = [newEntry, ...state.logs].slice(0, 100);
      return { logs: updated };
    }),

  clearLogs: () => set({ logs: [] }),

  toggleConsole: () =>
    set((state) => ({ isConsoleOpen: !state.isConsoleOpen })),

  toggleStats: () => set((state) => ({ isStatsOpen: !state.isStatsOpen })),

  triggerCameraReset: () =>
    set((state) => ({ cameraResetCount: state.cameraResetCount + 1 })),
}));
