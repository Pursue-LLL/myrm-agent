import { describe, it, expect } from 'vitest';
import {
  isAbsolutePath,
  normalizeDisplayPath,
  formatPathForDisplay,
  validateWorkspacePath,
} from '../pathValidation';

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
