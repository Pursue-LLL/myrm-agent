/**
 * [INPUT]
 * - @/components/features/chat-window/rules-hot-reload/useWorkspaceRulesStore
 *
 * [OUTPUT]
 * - Unit test suite for useWorkspaceRulesStore state mutations, rule file diffing, and bypass toggles.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useWorkspaceRulesStore } from '../useWorkspaceRulesStore';

describe('useWorkspaceRulesStore', () => {
  beforeEach(() => {
    useWorkspaceRulesStore.getState().resetStore();
  });

  it('should initialize with default empty state', () => {
    const state = useWorkspaceRulesStore.getState();
    expect(state.ruleFiles).toHaveLength(0);
    expect(state.combinedHash).toBe('00000000');
    expect(state.bypassRules).toBe(false);
    expect(state.isReloading).toBe(false);
    expect(state.notificationMessage).toBeNull();
  });

  it('should set rule files, compute combined hash, and record toast notification', () => {
    const store = useWorkspaceRulesStore.getState();
    const diffs = store.setRuleFiles([
      {
        path: '/workspace/AGENTS.md',
        filename: 'AGENTS.md',
        content: '# Guidelines',
        hash: 'hash1111',
        lastModified: 1000,
        sizeBytes: 12,
      },
    ]);

    expect(diffs).toHaveLength(1);
    expect(diffs[0].diffType).toBe('added');

    const updated = useWorkspaceRulesStore.getState();
    expect(updated.ruleFiles).toHaveLength(1);
    expect(updated.combinedHash).not.toBe('00000000');
    expect(updated.notificationMessage).toContain('AGENTS.md (新增)');
  });

  it('should upsert new and existing rule files seamlessly', () => {
    const store = useWorkspaceRulesStore.getState();

    // 插入新文件
    const inserted = store.upsertRuleFile({
      path: '/workspace/CLAUDE.md',
      filename: 'CLAUDE.md',
      content: 'Rule 1',
    });
    expect(inserted).toBe(true);
    expect(useWorkspaceRulesStore.getState().ruleFiles).toHaveLength(1);

    const firstHash = useWorkspaceRulesStore.getState().ruleFiles[0].hash;

    // 修改已存在文件
    store.upsertRuleFile({
      path: '/workspace/CLAUDE.md',
      filename: 'CLAUDE.md',
      content: 'Rule 1 updated',
    });

    const updatedFiles = useWorkspaceRulesStore.getState().ruleFiles;
    expect(updatedFiles).toHaveLength(1);
    expect(updatedFiles[0].hash).not.toBe(firstHash);
    expect(updatedFiles[0].content).toBe('Rule 1 updated');
  });

  it('should remove existing rule file and return false for non-existent file', () => {
    const store = useWorkspaceRulesStore.getState();
    store.upsertRuleFile({
      path: '/workspace/AGENTS.md',
      filename: 'AGENTS.md',
      content: 'Content',
    });

    const removedNonExistent = store.removeRuleFile('UNKNOWN.md');
    expect(removedNonExistent).toBe(false);

    const removed = store.removeRuleFile('AGENTS.md');
    expect(removed).toBe(true);
    expect(useWorkspaceRulesStore.getState().ruleFiles).toHaveLength(0);
    expect(useWorkspaceRulesStore.getState().combinedHash).toBe('00000000');
  });

  it('should toggle and set bypassRules flag', () => {
    const store = useWorkspaceRulesStore.getState();
    expect(store.bypassRules).toBe(false);

    store.toggleBypassRules();
    expect(useWorkspaceRulesStore.getState().bypassRules).toBe(true);

    store.setBypassRules(false);
    expect(useWorkspaceRulesStore.getState().bypassRules).toBe(false);
  });

  it('should trigger reloadRules and dismiss notifications', async () => {
    const store = useWorkspaceRulesStore.getState();
    store.upsertRuleFile({
      path: '/workspace/AGENTS.md',
      filename: 'AGENTS.md',
      content: 'Stable Rules',
    });

    const diffs = await store.reloadRules('manual_reload');
    expect(diffs).toHaveLength(0);
    expect(useWorkspaceRulesStore.getState().notificationMessage).toContain('未发现文件变更');

    store.dismissNotification();
    expect(useWorkspaceRulesStore.getState().notificationMessage).toBeNull();
  });
});
