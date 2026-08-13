/**
 * Tests for desktop inspector turn engagement lifecycle.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';

describe('useDesktopInspectorStore turn engagement', () => {
  beforeEach(() => {
    useDesktopInspectorStore.getState().reset();
  });

  it('markTurnEngaged sets engagedInTurn', () => {
    useDesktopInspectorStore.getState().markTurnEngaged();
    expect(useDesktopInspectorStore.getState().engagedInTurn).toBe(true);
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

    useDesktopInspectorStore.getState().releaseTurnEngagement();

    // A panel the user opened manually must survive unrelated turns.
    expect(useDesktopInspectorStore.getState().engagedInTurn).toBe(false);
    expect(useDesktopInspectorStore.getState().isOpen).toBe(true);
    expect(useDesktopInspectorStore.getState().viewData).not.toBeNull();
  });

  it('releaseTurnEngagement fully clears state after an engaged desktop turn', () => {
    useDesktopInspectorStore.getState().markTurnEngaged();
    useDesktopInspectorStore.getState().setDesktopActive(true);
    useDesktopInspectorStore.getState().openPanel();
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

    useDesktopInspectorStore.getState().releaseTurnEngagement();

    const state = useDesktopInspectorStore.getState();
    expect(state.engagedInTurn).toBe(false);
    expect(state.isDesktopActive).toBe(false);
    expect(state.isOpen).toBe(false);
    expect(state.viewData).toBeNull();
    expect(state.selectedElement).toBeNull();
  });

  it('reset clears engagedInTurn', () => {
    useDesktopInspectorStore.getState().markTurnEngaged();
    useDesktopInspectorStore.getState().reset();
    expect(useDesktopInspectorStore.getState().engagedInTurn).toBe(false);
  });
});
