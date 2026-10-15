/**
 * Three.js 与 WebGL 交互沙箱播放器类型定义
 */

export type SandboxCameraMode = 'orbit' | 'pointer_lock';

export type SandboxViewportMode = 'inline' | 'pip' | 'fullscreen';

export interface WebGLPerformanceMetrics {
  fps: number;
  drawCalls: number;
  triangles: number;
  geometries: number;
  textures: number;
  memoryMb?: number;
}

export type WebGLLogLevel = 'info' | 'warn' | 'error';

export interface WebGLLogEntry {
  id: string;
  level: WebGLLogLevel;
  message: string;
  timestamp: string;
  source?: 'shader' | 'texture' | 'runtime' | 'system';
  shaderInfo?: {
    type: 'vertex' | 'fragment';
    infoLog: string;
  };
}

export interface WebGLSelfHealingDossier {
  sceneId: string;
  errorMessage: string;
  source: string;
  timestamp: string;
  metricsAtFailure?: WebGLPerformanceMetrics;
  repairInstructionPrompt: string;
}

export interface ThreeJsSandboxConfig {
  autoOrbit: boolean;
  enablePointerLock: boolean;
  showPerformanceStats: boolean;
  showConsoleDrawer: boolean;
  backgroundTheme: 'dark' | 'transparent';
}
