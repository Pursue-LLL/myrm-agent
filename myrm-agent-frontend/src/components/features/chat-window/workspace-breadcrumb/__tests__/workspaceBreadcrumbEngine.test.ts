/**
 * [INPUT]
 * - @/components/features/chat-window/workspace-breadcrumb/workspaceBreadcrumbEngine
 *
 * [OUTPUT]
 * - Unit test suite for detectPlatform, parseWorkspacePath, truncatePathSegments, dispatchWorkspaceRevealEvent.
 */

import { describe, it, expect, vi } from 'vitest';
import {
  detectPlatform,
  parseWorkspacePath,
  truncatePathSegments,
  dispatchWorkspaceRevealEvent,
} from '../workspaceBreadcrumbEngine';
import type { PathSegment } from '../workspaceBreadcrumbTypes';

describe('workspaceBreadcrumbEngine', () => {
  describe('detectPlatform', () => {
    it('should detect darwin for macOS userAgent strings', () => {
      expect(detectPlatform('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')).toBe('darwin');
      expect(detectPlatform('Darwin 23.4.0')).toBe('darwin');
    });

    it('should detect win32 for Windows userAgent strings', () => {
      expect(detectPlatform('Mozilla/5.0 (Windows NT 10.0; Win64; x64)')).toBe('win32');
    });

    it('should fallback to linux for other userAgent strings', () => {
      expect(detectPlatform('Mozilla/5.0 (X11; Linux x86_64)')).toBe('linux');
      expect(detectPlatform('')).toBe('linux');
    });
  });

  describe('parseWorkspacePath', () => {
    it('should handle empty or whitespace paths with sensible defaults', () => {
      const posixDefault = parseWorkspacePath('', 'darwin');
      expect(posixDefault.rawPath).toBe('');
      expect(posixDefault.normalizedPath).toBe('/');
      expect(posixDefault.segments).toHaveLength(1);
      expect(posixDefault.segments[0].isRoot).toBe(true);

      const winDefault = parseWorkspacePath('   ', 'win32');
      expect(winDefault.normalizedPath).toBe('C:\\');
      expect(winDefault.segments).toHaveLength(1);
    });

    it('should parse POSIX absolute paths correctly', () => {
      const parsed = parseWorkspacePath('/Users/testuser/projects/myrm', 'darwin');
      expect(parsed.isSandbox).toBe(false);
      expect(parsed.normalizedPath).toBe('/Users/testuser/projects/myrm');
      expect(parsed.segments).toHaveLength(5);
      expect(parsed.segments[0].name).toBe('/');
      expect(parsed.segments[0].isRoot).toBe(true);
      expect(parsed.segments[1].name).toBe('Users');
      expect(parsed.segments[1].fullPath).toBe('/Users');
      expect(parsed.segments[4].name).toBe('myrm');
      expect(parsed.segments[4].isLeaf).toBe(true);
    });

    it('should parse Windows absolute paths correctly', () => {
      const parsed = parseWorkspacePath('C:\\Users\\Project\\dist', 'win32');
      expect(parsed.isSandbox).toBe(false);
      expect(parsed.normalizedPath).toBe('C:\\Users\\Project\\dist');
      expect(parsed.segments).toHaveLength(4);
      expect(parsed.segments[0].name).toBe('C:');
      expect(parsed.segments[0].isRoot).toBe(true);
      expect(parsed.segments[3].name).toBe('dist');
      expect(parsed.segments[3].isLeaf).toBe(true);
    });

    it('should detect sandbox environments correctly', () => {
      const sandboxPosix = parseWorkspacePath('/sandbox/workspace/src', 'linux');
      expect(sandboxPosix.isSandbox).toBe(true);

      const virtualSandbox = parseWorkspacePath('/virtual-sandbox/project', 'darwin');
      expect(virtualSandbox.isSandbox).toBe(true);
    });
  });

  describe('truncatePathSegments', () => {
    it('should return all segments when count is less than or equal to maxVisible', () => {
      const segments: PathSegment[] = [
        { name: '/', fullPath: '/', isRoot: true, isLeaf: false },
        { name: 'app', fullPath: '/app', isRoot: false, isLeaf: true },
      ];

      const truncated = truncatePathSegments(segments, 3);
      expect(truncated).toHaveLength(2);
      expect(truncated).toEqual(segments);
    });

    it('should collapse intermediate segments with ellipsis when exceeding maxVisible', () => {
      const segments: PathSegment[] = [
        { name: '/', fullPath: '/', isRoot: true, isLeaf: false },
        { name: 'Users', fullPath: '/Users', isRoot: false, isLeaf: false },
        { name: 'admin', fullPath: '/Users/admin', isRoot: false, isLeaf: false },
        { name: 'projects', fullPath: '/Users/admin/projects', isRoot: false, isLeaf: false },
        { name: 'myrm', fullPath: '/Users/admin/projects/myrm', isRoot: false, isLeaf: true },
      ];

      const truncated = truncatePathSegments(segments, 3);
      expect(truncated).toHaveLength(3);
      expect(truncated[0].name).toBe('/');
      expect(truncated[1].name).toBe('...');
      expect(truncated[2].name).toBe('myrm');
      expect(truncated[2].isLeaf).toBe(true);
    });
  });

  describe('dispatchWorkspaceRevealEvent', () => {
    it('should dispatch custom DOM event when in browser environment', () => {
      const spyDispatch = vi.spyOn(window, 'dispatchEvent');

      const result = dispatchWorkspaceRevealEvent({
        action: 'finder',
        path: '/test/path',
        timestamp: 1000,
      });

      expect(result).toBe(true);
      expect(spyDispatch).toHaveBeenCalled();
      spyDispatch.mockRestore();
    });
  });
});
