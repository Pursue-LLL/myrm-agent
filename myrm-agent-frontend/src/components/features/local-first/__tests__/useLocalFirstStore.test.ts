import { beforeEach, describe, expect, it } from 'vitest';
import { useLocalFirstStore } from '../useLocalFirstStore';

describe('useLocalFirstStore', () => {
  beforeEach(() => {
    useLocalFirstStore.getState().reset();
  });

  it('initializes with default state', () => {
    const state = useLocalFirstStore.getState();
    expect(state.inputText).toBe('');
    expect(state.lastSanitizeResult).toBeNull();
    expect(state.transformedText).toBe('');
    expect(state.activeBackend).toBe('local_storage');
    expect(state.roamingRecords).toEqual({});
    expect(state.sceneConfig.renderMode).toBe('webgpu_3d');
    expect(state.sceneConfig.nodesCount).toBe(12);
  });

  it('updates input text and performs local sanitize', () => {
    useLocalFirstStore.getState().setInputText('电话 13700002222');
    const result = useLocalFirstStore.getState().runLocalSanitize();

    expect(result.maskedCount).toBe(1);
    expect(result.sanitizedText).toBe('电话 137****2222');
    expect(useLocalFirstStore.getState().inputText).toBe('电话 137****2222');
    expect(useLocalFirstStore.getState().lastSanitizeResult).toEqual(result);
  });

  it('performs local format conversion', () => {
    const json = JSON.stringify([{ id: 1, name: 'Item' }]);
    const csv = useLocalFirstStore.getState().runFormatConvert(json, 'csv');

    expect(csv).toContain('id,name');
    expect(csv).toContain('1,Item');
    expect(useLocalFirstStore.getState().transformedText).toBe(csv);
  });

  it('switches active storage backend', () => {
    useLocalFirstStore.getState().setActiveBackend('upstash_redis');
    expect(useLocalFirstStore.getState().activeBackend).toBe('upstash_redis');
  });

  it('saves and retrieves roaming state with auto-incrementing version', () => {
    useLocalFirstStore.getState().setActiveBackend('indexed_db');

    const record1 = useLocalFirstStore
      .getState()
      .saveRoamingState('bookmarks', ['doc-1', 'doc-2']);
    expect(record1.version).toBe(1);
    expect(record1.backend).toBe('indexed_db');

    const data = useLocalFirstStore
      .getState()
      .getRoamingState<string[]>('bookmarks');
    expect(data).toEqual(['doc-1', 'doc-2']);

    const record2 = useLocalFirstStore
      .getState()
      .saveRoamingState('bookmarks', ['doc-1', 'doc-2', 'doc-3']);
    expect(record2.version).toBe(2);

    expect(
      useLocalFirstStore.getState().getRoamingState('non-existent-key'),
    ).toBeNull();
  });

  it('updates scene config for WebGPU meta artifact', () => {
    useLocalFirstStore.getState().updateSceneConfig({
      renderMode: 'canvas_2d_fallback',
      nodesCount: 24,
      isHardwareAccelerated: false,
    });

    const config = useLocalFirstStore.getState().sceneConfig;
    expect(config.renderMode).toBe('canvas_2d_fallback');
    expect(config.nodesCount).toBe(24);
    expect(config.isHardwareAccelerated).toBe(false);
  });

  it('resets all state on reset()', () => {
    useLocalFirstStore.getState().setInputText('dirty');
    useLocalFirstStore.getState().setActiveBackend('memory');
    useLocalFirstStore.getState().reset();

    const state = useLocalFirstStore.getState();
    expect(state.inputText).toBe('');
    expect(state.activeBackend).toBe('local_storage');
    expect(state.sceneConfig.renderMode).toBe('webgpu_3d');
  });
});
