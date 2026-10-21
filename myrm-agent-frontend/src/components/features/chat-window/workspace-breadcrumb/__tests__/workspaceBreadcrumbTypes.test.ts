/**
 * [INPUT]
 * - @/components/features/chat-window/workspace-breadcrumb/workspaceBreadcrumbTypes
 *
 * [OUTPUT]
 * - Type definition assertions and runtime payload contract validations for Item 197.
 */

import { describe, it, expect } from 'vitest';
import type {
  PathSegment,
  PlatformKind,
  WorkspaceLocationInfo,
  WorkspaceRevealAction,
  WorkspaceRevealEventPayload,
  WorkspaceBreadcrumbStoreState,
} from '../workspaceBreadcrumbTypes';

describe('WorkspaceBreadcrumbTypes Contracts', () => {
  it('should conform to PathSegment contract', () => {
    const segment: PathSegment = {
      name: 'src',
      fullPath: '/workspace/src',
      isRoot: false,
      isLeaf: true,
    };

    expect(segment.name).toBe('src');
    expect(segment.fullPath).toBe('/workspace/src');
    expect(segment.isRoot).toBe(false);
    expect(segment.isLeaf).toBe(true);
  });

  it('should accept valid PlatformKind values', () => {
    const platforms: PlatformKind[] = ['darwin', 'win32', 'linux'];
    expect(platforms).toHaveLength(3);
  });

  it('should accept valid WorkspaceRevealAction values', () => {
    const actions: WorkspaceRevealAction[] = ['finder', 'terminal', 'copy_path'];
    expect(actions).toHaveLength(3);
  });

  it('should construct a valid WorkspaceLocationInfo object', () => {
    const info: WorkspaceLocationInfo = {
      rawPath: '/Users/test/workspace',
      normalizedPath: '/Users/test/workspace',
      segments: [
        { name: '/', fullPath: '/', isRoot: true, isLeaf: false },
        { name: 'Users', fullPath: '/Users', isRoot: false, isLeaf: false },
        { name: 'test', fullPath: '/Users/test', isRoot: false, isLeaf: false },
        { name: 'workspace', fullPath: '/Users/test/workspace', isRoot: false, isLeaf: true },
      ],
      platform: 'darwin',
      isSandbox: false,
    };

    expect(info.platform).toBe('darwin');
    expect(info.isSandbox).toBe(false);
    expect(info.segments).toHaveLength(4);
    expect(info.segments[0].isRoot).toBe(true);
    expect(info.segments[3].isLeaf).toBe(true);
  });

  it('should conform to WorkspaceRevealEventPayload and StoreState contracts', () => {
    const payload: WorkspaceRevealEventPayload = {
      action: 'finder',
      path: '/Users/test/project',
      timestamp: 1760000000000,
    };

    const state: WorkspaceBreadcrumbStoreState = {
      workspacePathByChatId: { chat_1: '/Users/test/project' },
      activeChatId: 'chat_1',
      defaultPath: '/workspace',
      lastRevealedAction: 'finder',
      isCopied: false,
    };

    expect(payload.action).toBe('finder');
    expect(state.activeChatId).toBe('chat_1');
    expect(state.workspacePathByChatId.chat_1).toBe('/Users/test/project');
  });
});
