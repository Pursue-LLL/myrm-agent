import { describe, it, expect } from 'vitest';
import { isImeComposing } from '../imeUtils';
import { parseTitleIndex, disambiguateChatTitle } from '../titleUtils';
import {
  isAbsolutePath,
  normalizePath,
  normalizeDisplayPath,
  formatPathForDisplay,
  validateWorkspacePath,
} from '../pathValidation';
import { resolveSkillDescription } from '../skillUtils';
import { isRecord, asRecord, safeGet } from '../typeUtils';

type ImeEventLike = {
  key?: string;
  keyCode?: number;
  isComposing?: boolean;
  nativeEvent?: {
    isComposing?: boolean;
  };
};

describe('Frontend Polish Utilities Suite', () => {
  describe('imeUtils - isImeComposing', () => {
    it('returns true when nativeEvent.isComposing is true', () => {
      const event: ImeEventLike = { nativeEvent: { isComposing: true } };
      expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
    });

    it('returns true when event.isComposing is true', () => {
      const event: ImeEventLike = { isComposing: true };
      expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
    });

    it('returns true when event.key is Process', () => {
      const event: ImeEventLike = { key: 'Process', isComposing: false };
      expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
    });

    it('returns true when event.keyCode is 229', () => {
      const event: ImeEventLike = { keyCode: 229, isComposing: false };
      expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
    });

    it('returns false for normal Enter press without IME composition', () => {
      const event: ImeEventLike = {
        key: 'Enter',
        keyCode: 13,
        isComposing: false,
        nativeEvent: { isComposing: false },
      };
      expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(false);
    });
  });

  describe('titleUtils - parseTitleIndex & disambiguateChatTitle', () => {
    it('parses base and index correctly', () => {
      expect(parseTitleIndex('方案讨论')).toEqual({ base: '方案讨论', index: 1 });
      expect(parseTitleIndex('方案讨论 (2)')).toEqual({ base: '方案讨论', index: 2 });
      expect(parseTitleIndex('方案讨论 (10)')).toEqual({ base: '方案讨论', index: 10 });
    });

    it('returns candidate title when no collision exists', () => {
      expect(disambiguateChatTitle('方案讨论', ['其他会话', '历史记录'])).toBe('方案讨论');
    });

    it('increments index cleanly when collision exists', () => {
      expect(disambiguateChatTitle('方案讨论', ['方案讨论'])).toBe('方案讨论 (2)');
      expect(disambiguateChatTitle('方案讨论', ['方案讨论', '方案讨论 (2)'])).toBe('方案讨论 (3)');
      expect(disambiguateChatTitle('方案讨论 (2)', ['方案讨论', '方案讨论 (2)'])).toBe('方案讨论 (3)');
    });
  });

  describe('pathValidation - Windows, POSIX & UNC support', () => {
    it('identifies absolute paths correctly across platforms', () => {
      expect(isAbsolutePath('/usr/local/bin')).toBe(true);
      expect(isAbsolutePath('C:\\Windows\\System32')).toBe(true);
      expect(isAbsolutePath('d:/workspace/code')).toBe(true);
      expect(isAbsolutePath('\\\\nas-server\\share\\repo')).toBe(true);
      expect(isAbsolutePath('relative/path')).toBe(false);
    });

    it('normalizes display paths with unified forward slashes and capitalized drive letters', () => {
      expect(normalizeDisplayPath('c:\\my projects\\agent\\')).toBe('C:/my projects/agent');
      expect(normalizeDisplayPath('\\\\server\\share\\subfolder\\')).toBe('//server/share/subfolder');
      expect(normalizeDisplayPath('/var/log/myrm//')).toBe('/var/log/myrm');
    });

    it('formats paths gracefully for UI chips with center truncation', () => {
      expect(formatPathForDisplay('/short/path', 30)).toBe('/short/path');
      const longPath = 'C:/Users/Administrator/Projects/DeepResearch/SubModules/App';
      const formatted = formatPathForDisplay(longPath, 25);
      expect(formatted).toContain('...');
      expect(formatted.length).toBeLessThanOrEqual(25);
    });

    it('validates and normalizes workspace paths including ~, POSIX, Windows and UNC', () => {
      // 1. Empty / whitespace
      expect(validateWorkspacePath('')).toEqual({
        valid: false,
        normalizedPath: '',
        errorKey: 'workspacePathEmpty',
      });
      expect(validateWorkspacePath('   ')).toEqual({
        valid: false,
        normalizedPath: '',
        errorKey: 'workspacePathEmpty',
      });

      // 2. Invalid control chars
      expect(validateWorkspacePath('/path/with\nnewline')).toEqual({
        valid: false,
        normalizedPath: '',
        errorKey: 'workspacePathInvalidChars',
      });
      expect(validateWorkspacePath('/path/with\x00null')).toEqual({
        valid: false,
        normalizedPath: '',
        errorKey: 'workspacePathInvalidChars',
      });

      // 3. Home directory paths ~
      expect(validateWorkspacePath('~')).toEqual({
        valid: true,
        normalizedPath: '~',
      });
      expect(validateWorkspacePath('~/projects/my-app')).toEqual({
        valid: true,
        normalizedPath: '~/projects/my-app',
      });
      expect(validateWorkspacePath('~\\projects\\my-app\\')).toEqual({
        valid: true,
        normalizedPath: '~/projects/my-app',
      });

      // 4. Absolute POSIX & Windows & UNC
      expect(validateWorkspacePath('/var/www/project/')).toEqual({
        valid: true,
        normalizedPath: '/var/www/project',
      });
      expect(validateWorkspacePath('c:\\Users\\Dev\\Repo\\')).toEqual({
        valid: true,
        normalizedPath: 'C:/Users/Dev/Repo',
      });
      expect(validateWorkspacePath('\\\\nas-server\\share\\repo\\')).toEqual({
        valid: true,
        normalizedPath: '//nas-server/share/repo',
      });

      // 5. Relative paths (invalid)
      expect(validateWorkspacePath('relative/path/project')).toEqual({
        valid: false,
        normalizedPath: '',
        errorKey: 'workspacePathMustBeAbsolute',
      });
      expect(validateWorkspacePath('./subfolder')).toEqual({
        valid: false,
        normalizedPath: '',
        errorKey: 'workspacePathMustBeAbsolute',
      });
    });
  });

  describe('skillUtils - resolveSkillDescription', () => {
    it('returns skill description if present and non-empty', () => {
      expect(resolveSkillDescription({ description: 'A helpful skill' }, 'No description')).toBe('A helpful skill');
    });

    it('returns fallback when description is missing, null or empty whitespace', () => {
      expect(resolveSkillDescription({ description: '' }, '暂无描述')).toBe('暂无描述');
      expect(resolveSkillDescription({ description: '   ' }, '暂无描述')).toBe('暂无描述');
      expect(resolveSkillDescription(null, '暂无描述')).toBe('暂无描述');
      expect(resolveSkillDescription(undefined, '暂无描述')).toBe('暂无描述');
    });
  });

  describe('typeUtils - isRecord, asRecord & safeGet', () => {
    it('identifies plain records safely', () => {
      expect(isRecord({ a: 1 })).toBe(true);
      expect(isRecord(null)).toBe(false);
      expect(isRecord([1, 2, 3])).toBe(false);
      expect(isRecord('string')).toBe(false);
    });

    it('asRecord returns valid record or empty object', () => {
      expect(asRecord({ key: 'value' })).toEqual({ key: 'value' });
      expect(asRecord(null)).toEqual({});
      expect(asRecord('dirty')).toEqual({});
      expect(asRecord(undefined)).toEqual({});
    });

    it('safeGet safely retrieves nested attributes without crashing', () => {
      const complex = {
        metadata: {
          usage: {
            total_tokens: 1500,
          },
        },
      };
      expect(safeGet(complex, 'metadata.usage.total_tokens')).toBe(1500);
      expect(safeGet(complex, 'metadata.invalid.field', 'default')).toBe('default');
      expect(safeGet(null, 'any.path', 'fallback')).toBe('fallback');
    });
  });
});
