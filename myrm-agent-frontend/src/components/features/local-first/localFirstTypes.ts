export type StorageBackendType =
  | 'local_storage'
  | 'indexed_db'
  | 'upstash_redis'
  | 'memory';

export type TransformFormat = 'json' | 'yaml' | 'csv' | 'markdown_table';

export interface PrivacySanitizeResult {
  sanitizedText: string;
  maskedCount: number;
  detectedTypes: string[];
  executionTimeMs: number;
}

export interface RoamingStateRecord<T = unknown> {
  key: string;
  data: T;
  backend: StorageBackendType;
  version: number;
  updatedAt: number;
  checksum: string;
}

export type WebGPURenderMode = 'webgpu_3d' | 'canvas_2d_fallback';

export interface WebGPUArtifactSceneConfig {
  sceneId: string;
  renderMode: WebGPURenderMode;
  nodesCount: number;
  isHardwareAccelerated: boolean;
  status: 'ready' | 'rendering' | 'fallback';
}
