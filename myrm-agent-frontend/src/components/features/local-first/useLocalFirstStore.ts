import { create } from 'zustand';
import {
  buildRoamingRecord,
  convertJsonToFormat,
  sanitizeClientSideData,
} from './localFirstPrivacyEngine';
import {
  PrivacySanitizeResult,
  RoamingStateRecord,
  StorageBackendType,
  TransformFormat,
  WebGPUArtifactSceneConfig,
} from './localFirstTypes';

interface LocalFirstState {
  inputText: string;
  lastSanitizeResult: PrivacySanitizeResult | null;
  transformedText: string;
  activeBackend: StorageBackendType;
  roamingRecords: Record<string, RoamingStateRecord>;
  sceneConfig: WebGPUArtifactSceneConfig;

  setInputText: (text: string) => void;
  runLocalSanitize: (text?: string) => PrivacySanitizeResult;
  runFormatConvert: (jsonStr: string, targetFormat: TransformFormat) => string;
  setActiveBackend: (backend: StorageBackendType) => void;
  saveRoamingState: <T>(key: string, data: T) => RoamingStateRecord<T>;
  getRoamingState: <T>(key: string) => T | null;
  updateSceneConfig: (updates: Partial<WebGPUArtifactSceneConfig>) => void;
  reset: () => void;
}

const DEFAULT_SCENE_CONFIG: WebGPUArtifactSceneConfig = {
  sceneId: 'default-meta-canvas',
  renderMode: 'webgpu_3d',
  nodesCount: 12,
  isHardwareAccelerated: true,
  status: 'ready',
};

export const useLocalFirstStore = create<LocalFirstState>((set, get) => ({
  inputText: '',
  lastSanitizeResult: null,
  transformedText: '',
  activeBackend: 'local_storage',
  roamingRecords: {},
  sceneConfig: DEFAULT_SCENE_CONFIG,

  setInputText: (text: string): void => {
    set({ inputText: text });
  },

  runLocalSanitize: (text?: string): PrivacySanitizeResult => {
    const raw = text !== undefined ? text : get().inputText;
    const result = sanitizeClientSideData(raw);
    set({
      lastSanitizeResult: result,
      inputText: result.sanitizedText,
    });
    return result;
  },

  runFormatConvert: (
    jsonStr: string,
    targetFormat: TransformFormat,
  ): string => {
    const converted = convertJsonToFormat(jsonStr, targetFormat);
    set({ transformedText: converted });
    return converted;
  },

  setActiveBackend: (backend: StorageBackendType): void => {
    set({ activeBackend: backend });
  },

  saveRoamingState: <T>(key: string, data: T): RoamingStateRecord<T> => {
    const existing = get().roamingRecords[key];
    const nextVersion = existing ? existing.version + 1 : 1;
    const record = buildRoamingRecord(
      key,
      data,
      get().activeBackend,
      nextVersion,
    );

    set((state) => ({
      roamingRecords: {
        ...state.roamingRecords,
        [key]: record as RoamingStateRecord,
      },
    }));

    return record;
  },

  getRoamingState: <T>(key: string): T | null => {
    const record = get().roamingRecords[key];
    if (!record) {
      return null;
    }
    return record.data as T;
  },

  updateSceneConfig: (updates: Partial<WebGPUArtifactSceneConfig>): void => {
    set((state) => ({
      sceneConfig: {
        ...state.sceneConfig,
        ...updates,
      },
    }));
  },

  reset: (): void => {
    set({
      inputText: '',
      lastSanitizeResult: null,
      transformedText: '',
      activeBackend: 'local_storage',
      roamingRecords: {},
      sceneConfig: DEFAULT_SCENE_CONFIG,
    });
  },
}));
