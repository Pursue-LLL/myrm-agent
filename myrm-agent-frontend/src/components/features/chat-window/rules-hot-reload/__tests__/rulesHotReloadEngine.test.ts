/**
 * [INPUT]
 * - @/components/features/chat-window/rules-hot-reload/rulesHotReloadEngine
 * - @/components/features/chat-window/rules-hot-reload/rulesHotReloadTypes
 *
 * [OUTPUT]
 * - Unit test suite for pure computational functions in rulesHotReloadEngine.
 */

import { describe, it, expect, vi } from 'vitest';
import {
  isKnownRuleFileName,
  computeStringHash,
  computeCombinedHash,
  diffRuleFiles,
  formatReloadToastMessage,
  dispatchRulesReloadEvent,
} from '../rulesHotReloadEngine';
import type { WorkspaceRuleFile } from '../rulesHotReloadTypes';

describe('rulesHotReloadEngine', () => {
  describe('isKnownRuleFileName', () => {
    it('should recognize known rule files regardless of casing', () => {
      expect(isKnownRuleFileName('AGENTS.md')).toBe(true);
      expect(isKnownRuleFileName('agents.md')).toBe(true);
      expect(isKnownRuleFileName('CLAUDE.md')).toBe(true);
      expect(isKnownRuleFileName('append-system.md')).toBe(true);
      expect(isKnownRuleFileName('.cursorrules')).toBe(true);
      expect(isKnownRuleFileName('SYSTEM.md')).toBe(true);
    });

    it('should return false for arbitrary non-rule files', () => {
      expect(isKnownRuleFileName('package.json')).toBe(false);
      expect(isKnownRuleFileName('index.ts')).toBe(false);
      expect(isKnownRuleFileName('rules.txt')).toBe(false);
    });
  });

  describe('computeStringHash', () => {
    it('should compute deterministic 8-char hex hash', () => {
      const hash1 = computeStringHash('Strict TypeScript without any');
      const hash2 = computeStringHash('Strict TypeScript without any');
      const hash3 = computeStringHash('Different rule contents');

      expect(hash1).toHaveLength(8);
      expect(hash1).toBe(hash2);
      expect(hash1).not.toBe(hash3);
    });
  });

  describe('computeCombinedHash', () => {
    it('should return 00000000 for empty file set', () => {
      expect(computeCombinedHash([])).toBe('00000000');
    });

    it('should generate stable hash independent of file array order', () => {
      const fileA: WorkspaceRuleFile = {
        path: '/AGENTS.md',
        filename: 'AGENTS.md',
        content: 'content A',
        hash: 'aaaa1111',
        lastModified: 1000,
        sizeBytes: 9,
      };

      const fileB: WorkspaceRuleFile = {
        path: '/CLAUDE.md',
        filename: 'CLAUDE.md',
        content: 'content B',
        hash: 'bbbb2222',
        lastModified: 2000,
        sizeBytes: 9,
      };

      const hashOrder1 = computeCombinedHash([fileA, fileB]);
      const hashOrder2 = computeCombinedHash([fileB, fileA]);

      expect(hashOrder1).toBe(hashOrder2);
      expect(hashOrder1).toHaveLength(8);
    });
  });

  describe('diffRuleFiles', () => {
    const originalFile: WorkspaceRuleFile = {
      path: '/AGENTS.md',
      filename: 'AGENTS.md',
      content: 'original',
      hash: 'orig1234',
      lastModified: 1000,
      sizeBytes: 8,
    };

    it('should detect added rule files', () => {
      const diffs = diffRuleFiles([], [originalFile]);
      expect(diffs).toHaveLength(1);
      expect(diffs[0].diffType).toBe('added');
      expect(diffs[0].filename).toBe('AGENTS.md');
      expect(diffs[0].currentHash).toBe('orig1234');
    });

    it('should detect modified rule files', () => {
      const updatedFile: WorkspaceRuleFile = {
        ...originalFile,
        content: 'updated',
        hash: 'updt5678',
      };

      const diffs = diffRuleFiles([originalFile], [updatedFile]);
      expect(diffs).toHaveLength(1);
      expect(diffs[0].diffType).toBe('modified');
      expect(diffs[0].previousHash).toBe('orig1234');
      expect(diffs[0].currentHash).toBe('updt5678');
    });

    it('should detect removed rule files', () => {
      const diffs = diffRuleFiles([originalFile], []);
      expect(diffs).toHaveLength(1);
      expect(diffs[0].diffType).toBe('removed');
      expect(diffs[0].previousHash).toBe('orig1234');
    });
  });

  describe('formatReloadToastMessage', () => {
    it('should format message for unchanged files on manual reload', () => {
      const msg = formatReloadToastMessage([], 'manual_reload');
      expect(msg).toContain('未发现文件变更');
    });

    it('should format message describing added and modified files', () => {
      const msg = formatReloadToastMessage(
        [
          { filename: 'AGENTS.md', diffType: 'modified' },
          { filename: 'CLAUDE.md', diffType: 'added' },
        ],
        'file_watcher',
      );

      expect(msg).toContain('AGENTS.md (已修改)');
      expect(msg).toContain('CLAUDE.md (新增)');
      expect(msg).toContain('免重启即刻生效');
    });
  });

  describe('dispatchRulesReloadEvent', () => {
    it('should dispatch custom DOM event with payload', () => {
      const spy = vi.spyOn(window, 'dispatchEvent');

      const dispatched = dispatchRulesReloadEvent({
        source: 'manual_reload',
        diffs: [],
        combinedHash: '12345678',
        timestamp: 1000,
      });

      expect(dispatched).toBe(true);
      expect(spy).toHaveBeenCalled();
      spy.mockRestore();
    });
  });
});
