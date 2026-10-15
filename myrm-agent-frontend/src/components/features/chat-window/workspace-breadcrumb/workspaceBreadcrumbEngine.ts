/**
 * [INPUT]
 * - @/components/features/chat-window/workspace-breadcrumb/workspaceBreadcrumbTypes
 *
 * [OUTPUT]
 * - detectPlatform, parseWorkspacePath, truncatePathSegments, dispatchWorkspaceRevealEvent
 *
 * [POS]
 * Pure computation engine for Item 197 (P1): WorkspaceBreadcrumbPathAndDesktopRevealSuite.
 * Normalizes multi-platform workspace paths, splits hierarchical breadcrumb segments,
 * and dispatches desktop file manager / terminal bridge events.
 */

import type {
  PlatformKind,
  PathSegment,
  WorkspaceLocationInfo,
  WorkspaceRevealEventPayload,
} from './workspaceBreadcrumbTypes';

export function detectPlatform(userAgent?: string): PlatformKind {
  const ua = userAgent ?? (typeof navigator !== 'undefined' ? navigator.userAgent : '');
  const lower = ua.toLowerCase();
  if (lower.includes('mac') || lower.includes('darwin')) {
    return 'darwin';
  }
  if (lower.includes('win')) {
    return 'win32';
  }
  return 'linux';
}

export function parseWorkspacePath(
  rawPath: string,
  platformOverride?: PlatformKind,
): WorkspaceLocationInfo {
  const platform = platformOverride ?? detectPlatform();
  const trimmed = rawPath.trim();

  if (!trimmed) {
    const defaultRoot = platform === 'win32' ? 'C:\\' : '/';
    return {
      rawPath: '',
      normalizedPath: defaultRoot,
      segments: [{ name: defaultRoot, fullPath: defaultRoot, isRoot: true, isLeaf: true }],
      platform,
      isSandbox: false,
    };
  }

  const isWindows = platform === 'win32' || /^[a-zA-Z]:\\/.test(trimmed);
  const normalized = isWindows ? trimmed.replace(/\//g, '\\') : trimmed.replace(/\\/g, '/');

  const isSandbox =
    normalized.startsWith('/sandbox') ||
    normalized.startsWith('/workspace') ||
    normalized.includes('virtual-sandbox');

  const segments: PathSegment[] = [];

  if (isWindows) {
    // Windows 盘符与路径解析 (e.g. C:\Users\Project)
    const parts = normalized.split('\\').filter((p) => p.length > 0);
    let accumulated = '';
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      accumulated = i === 0 ? `${part}\\` : `${accumulated}${part}${i === parts.length - 1 ? '' : '\\'}`;
      segments.push({
        name: part,
        fullPath: accumulated,
        isRoot: i === 0,
        isLeaf: i === parts.length - 1,
      });
    }
  } else {
    // POSIX 路径解析 (e.g. /Users/yululiu/projects)
    const isAbsolute = normalized.startsWith('/');
    const parts = normalized.split('/').filter((p) => p.length > 0);

    if (isAbsolute) {
      segments.push({
        name: '/',
        fullPath: '/',
        isRoot: true,
        isLeaf: parts.length === 0,
      });
    }

    let accumulated = isAbsolute ? '' : '';
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      accumulated = `${accumulated}/${part}`;
      segments.push({
        name: part,
        fullPath: accumulated,
        isRoot: false,
        isLeaf: i === parts.length - 1,
      });
    }
  }

  return {
    rawPath,
    normalizedPath: normalized,
    segments: segments.length > 0 ? segments : [{ name: normalized, fullPath: normalized, isRoot: true, isLeaf: true }],
    platform,
    isSandbox,
  };
}

export function truncatePathSegments(
  segments: readonly PathSegment[],
  maxVisible = 3,
): readonly PathSegment[] {
  if (segments.length <= maxVisible) {
    return segments;
  }

  const first = segments[0];
  const last = segments[segments.length - 1];
  const ellipsisSegment: PathSegment = {
    name: '...',
    fullPath: segments[Math.floor(segments.length / 2)].fullPath,
    isRoot: false,
    isLeaf: false,
  };

  return [first, ellipsisSegment, last];
}

export function dispatchWorkspaceRevealEvent(payload: WorkspaceRevealEventPayload): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  try {
    const event = new CustomEvent('myrm:workspace-reveal', {
      detail: payload,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(event);
    return true;
  } catch {
    return false;
  }
}
