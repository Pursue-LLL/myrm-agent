/**
 * [INPUT]
 * - @/components/features/chat-window/rules-hot-reload/rulesHotReloadTypes
 *
 * [OUTPUT]
 * - Type definition assertions and runtime payload contract validations for Item 199.
 */

import { describe, it, expect } from 'vitest';
import type {
  WorkspaceRuleFile,
  RulesReloadSource,
  RuleDiffType,
  RuleFileDiff,
  RulesReloadEventPayload,
  WorkspaceRulesStoreState,
} from '../rulesHotReloadTypes';

describe('RulesHotReloadTypes Contracts', () => {
  it('should accept valid RulesReloadSource and RuleDiffType values', () => {
    const sources: RulesReloadSource[] = ['file_watcher', 'manual_reload', 'slash_command'];
    expect(sources).toHaveLength(3);

    const diffTypes: RuleDiffType[] = ['added', 'modified', 'removed'];
    expect(diffTypes).toHaveLength(3);
  });

  it('should construct a valid WorkspaceRuleFile entity', () => {
    const file: WorkspaceRuleFile = {
      path: '/workspace/AGENTS.md',
      filename: 'AGENTS.md',
      content: '# Project Guidelines',
      hash: 'a1b2c3d4',
      lastModified: 1760000000000,
      sizeBytes: 20,
    };

    expect(file.filename).toBe('AGENTS.md');
    expect(file.hash).toBe('a1b2c3d4');
    expect(file.sizeBytes).toBe(20);
  });

  it('should conform to RuleFileDiff and RulesReloadEventPayload contracts', () => {
    const diff: RuleFileDiff = {
      filename: 'CLAUDE.md',
      diffType: 'modified',
      previousHash: '11111111',
      currentHash: '22222222',
    };

    const payload: RulesReloadEventPayload = {
      source: 'file_watcher',
      diffs: [diff],
      combinedHash: 'abcdef01',
      timestamp: 1760000001000,
    };

    expect(payload.source).toBe('file_watcher');
    expect(payload.diffs).toHaveLength(1);
    expect(payload.diffs[0].diffType).toBe('modified');
    expect(payload.combinedHash).toBe('abcdef01');
  });

  it('should construct a valid WorkspaceRulesStoreState entity', () => {
    const state: WorkspaceRulesStoreState = {
      ruleFiles: [],
      combinedHash: '00000000',
      bypassRules: false,
      isReloading: false,
      lastReloadedAt: null,
      lastReloadSource: null,
      notificationMessage: null,
    };

    expect(state.ruleFiles).toHaveLength(0);
    expect(state.bypassRules).toBe(false);
    expect(state.combinedHash).toBe('00000000');
  });
});
