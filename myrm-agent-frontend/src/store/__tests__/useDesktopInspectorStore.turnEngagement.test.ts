/**
 * Tests for desktop inspector turn engagement lifecycle (per-chat ownership).
 */
import { beforeEach, describe, expect, it } from 'vitest';

import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';

describe('useDesktopInspectorStore turn engagement', () => {
  beforeEach(() => {
    useDesktopInspectorStore.getState().reset();
  });

  it('markTurnEngaged records the owning chat id', () => {
    useDesktopInspectorStore.getState().markTurnEngaged('c1');
    expect(useDesktopInspectorStore.getState().engagedChatId).toBe('c1');
  });

  it('markTurnEngaged ignores an empty chat id', () => {
    useDesktopInspectorStore.getState().markTurnEngaged('');
    expect(useDesktopInspectorStore.getState().engagedChatId).toBeNull();
  });

  it('releaseTurnEngagement is a no-op when the turn never engaged desktop events', () => {
    const state = useDesktopInspectorStore.getState();
    state.openPanel();
    state.updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/png',
      refs: {},
      appName: 'Calculator',
      windowTitle: '',
      scope: 'app',
      needsPermission: false,
      viewportWidth: 100,
      viewportHeight: 100,
      sourceChatId: 'c1',
      updatedAt: Date.now(),
    });

    useDesktopInspectorStore.getState().releaseTurnEngagement('c1');

    // A panel the user opened manually must survive unrelated turns.
    expect(useDesktopInspectorStore.getState().engagedChatId).toBeNull();
    expect(useDesktopInspectorStore.getState().isOpen).toBe(true);
    expect(useDesktopInspectorStore.getState().viewData).not.toBeNull();
  });

  it('releaseTurnEngagement is a no-op for a different chat (parallel panes)', () => {
    useDesktopInspectorStore.getState().markTurnEngaged('c1');
    useDesktopInspectorStore.getState().setDesktopActive(true);
    useDesktopInspectorStore.getState().openPanel();

    // Pane c2's turn ends: it must not tear down pane c1's engaged panel.
    useDesktopInspectorStore.getState().releaseTurnEngagement('c2');

    const state = useDesktopInspectorStore.getState();
    expect(state.engagedChatId).toBe('c1');
    expect(state.isDesktopActive).toBe(true);
    expect(state.isOpen).toBe(true);
  });

  it('releaseTurnEngagement fully clears state after the owning chat ends', () => {
    useDesktopInspectorStore.getState().markTurnEngaged('c1');
    useDesktopInspectorStore.getState().setDesktopActive(true);
    useDesktopInspectorStore.getState().openPanel();
    useDesktopInspectorStore.getState().setInstructionText('click ok');
    useDesktopInspectorStore.getState().updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/png',
      refs: {},
      appName: 'Calculator',
      windowTitle: '',
      scope: 'app',
      needsPermission: false,
      viewportWidth: 100,
      viewportHeight: 100,
      sourceChatId: 'c1',
      updatedAt: Date.now(),
    });

    useDesktopInspectorStore.getState().releaseTurnEngagement('c1');

    const state = useDesktopInspectorStore.getState();
    expect(state.engagedChatId).toBeNull();
    expect(state.isDesktopActive).toBe(false);
    expect(state.isOpen).toBe(false);
    expect(state.viewData).toBeNull();
    expect(state.selectedElement).toBeNull();
    expect(state.instructionText).toBe('');
  });

  it('reset clears engagedChatId', () => {
    useDesktopInspectorStore.getState().markTurnEngaged('c1');
    useDesktopInspectorStore.getState().reset();
    expect(useDesktopInspectorStore.getState().engagedChatId).toBeNull();
  });
});
