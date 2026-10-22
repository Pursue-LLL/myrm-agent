/**
 * Semantic Tool Group Store Unit Tests
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useSemanticToolGroupStore } from '../useSemanticToolGroupStore';

describe('useSemanticToolGroupStore', () => {
  beforeEach(() => {
    useSemanticToolGroupStore.getState().resetToDefault();
  });

  it('should initialize with standard_assistant preset', () => {
    const state = useSemanticToolGroupStore.getState();
    expect(state.preset).toBe('standard_assistant');
    expect(state.groups.runtime.enabled).toBe(true);
    expect(state.groups.runtime.securityLevel).toBe('isolated_sandbox');
  });

  it('should switch preset to strict_safe and update group configurations', () => {
    const store = useSemanticToolGroupStore.getState();
    store.setPreset('strict_safe');

    const updated = useSemanticToolGroupStore.getState();
    expect(updated.preset).toBe('strict_safe');
    expect(updated.groups.runtime.enabled).toBe(false);
    expect(updated.groups.filesystem.securityLevel).toBe('read_only');
  });

  it('should switch to custom preset when toggling an individual group or tool', () => {
    const store = useSemanticToolGroupStore.getState();
    store.toggleGroup('runtime', false);

    const updated = useSemanticToolGroupStore.getState();
    expect(updated.preset).toBe('custom');
    expect(updated.groups.runtime.enabled).toBe(false);

    // Toggle individual tool
    store.toggleIndividualTool('filesystem', 'fs_read_file');
    const afterToolToggle = useSemanticToolGroupStore.getState();
    expect(afterToolToggle.groups.filesystem.disabledToolIds).toContain('fs_read_file');
  });

  it('should export valid JSON and re-import properly', () => {
    const store = useSemanticToolGroupStore.getState();
    store.setGroupSecurityLevel('web', 'unrestricted');

    const jsonString = store.exportConfigJson();
    expect(jsonString).toContain('"version": "2.0.0"');

    // Reset and re-import
    store.resetToDefault();
    expect(useSemanticToolGroupStore.getState().groups.web.securityLevel).not.toBe('unrestricted');

    const importResult = store.importConfigJson(jsonString);
    expect(importResult.success).toBe(true);
    expect(useSemanticToolGroupStore.getState().groups.web.securityLevel).toBe('unrestricted');
  });

  it('should reject invalid JSON format on import', () => {
    const store = useSemanticToolGroupStore.getState();
    const result = store.importConfigJson('not-valid-json');
    expect(result.success).toBe(false);
    expect(result.error).toBeTruthy();
  });
});
