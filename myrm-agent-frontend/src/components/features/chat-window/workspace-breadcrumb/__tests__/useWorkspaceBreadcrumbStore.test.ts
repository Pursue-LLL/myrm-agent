/**
 * [INPUT]
 * - @/components/features/chat-window/workspace-breadcrumb/useWorkspaceBreadcrumbStore
 *
 * [OUTPUT]
 * - Unit test suite for useWorkspaceBreadcrumbStore actions and state mutations.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWorkspaceBreadcrumbStore } from '../useWorkspaceBreadcrumbStore';

describe('useWorkspaceBreadcrumbStore', () => {
  beforeEach(() => {
    useWorkspaceBreadcrumbStore.getState().resetStore();
    vi.restoreAllMocks();
  });

  it('should initialize with default empty state', () => {
    const state = useWorkspaceBreadcrumbStore.getState();
    expect(state.activeChatId).toBeNull();
    expect(state.workspacePathByChatId).toEqual({});
    expect(state.defaultPath).toBe('/workspace');
    expect(state.lastRevealedAction).toBeNull();
    expect(state.isCopied).toBe(false);
  });

  it('should set active chatId and record workspace path per session', () => {
    const store = useWorkspaceBreadcrumbStore.getState();
    store.setWorkspacePath('session_a', '/Users/alice/projects/demo');
    store.setActiveChatId('session_a');

    expect(useWorkspaceBreadcrumbStore.getState().activeChatId).toBe('session_a');
    expect(useWorkspaceBreadcrumbStore.getState().getCurrentPath()).toBe(
      '/Users/alice/projects/demo',
    );
  });

  it('should fallback to defaultPath when chatId has no custom workspace path', () => {
    const store = useWorkspaceBreadcrumbStore.getState();
    store.setDefaultPath('/var/default-workspace');
    store.setActiveChatId('unknown_session');

    expect(useWorkspaceBreadcrumbStore.getState().getCurrentPath()).toBe(
      '/var/default-workspace',
    );
  });

  it('should return parsed location info via getLocationInfo', () => {
    const store = useWorkspaceBreadcrumbStore.getState();
    store.setDefaultPath('/Users/dev/code');

    const info = store.getLocationInfo();
    expect(info.normalizedPath).toBe('/Users/dev/code');
    expect(info.segments.length).toBeGreaterThan(1);
  });

  it('should trigger revealInFinder and revealInTerminal', () => {
    const store = useWorkspaceBreadcrumbStore.getState();
    store.setDefaultPath('/Users/dev/repo');

    const finderDispatched = store.revealInFinder();
    expect(finderDispatched).toBe(true);
    expect(useWorkspaceBreadcrumbStore.getState().lastRevealedAction).toBe('finder');

    const terminalDispatched = store.revealInTerminal();
    expect(terminalDispatched).toBe(true);
    expect(useWorkspaceBreadcrumbStore.getState().lastRevealedAction).toBe('terminal');
  });

  it('should copy path to clipboard and set copied flag', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    const store = useWorkspaceBreadcrumbStore.getState();
    store.setDefaultPath('/Users/dev/my-app');

    const copied = await store.copyCurrentPath();
    expect(copied).toBe(true);
    expect(writeTextMock).toHaveBeenCalledWith('/Users/dev/my-app');
    expect(useWorkspaceBreadcrumbStore.getState().isCopied).toBe(true);
    expect(useWorkspaceBreadcrumbStore.getState().lastRevealedAction).toBe('copy_path');

    store.resetCopied();
    expect(useWorkspaceBreadcrumbStore.getState().isCopied).toBe(false);
  });
});
