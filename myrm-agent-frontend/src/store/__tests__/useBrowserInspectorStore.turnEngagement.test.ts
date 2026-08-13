/**
 * Tests for browser inspector turn engagement lifecycle.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';

describe('useBrowserInspectorStore turn engagement', () => {
  beforeEach(() => {
    useBrowserInspectorStore.getState().reset();
  });

  it('markTurnEngaged sets engagedInTurn', () => {
    useBrowserInspectorStore.getState().markTurnEngaged();
    expect(useBrowserInspectorStore.getState().engagedInTurn).toBe(true);
  });

  it('releaseTurnEngagement is a no-op when the turn never engaged browser events', () => {
    const state = useBrowserInspectorStore.getState();
    state.openPanel();
    state.updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/jpeg',
      refs: {},
      pageUrl: 'https://example.com',
      pageTitle: 'Example',
      viewportWidth: 1280,
      viewportHeight: 720,
      sourceChatId: 'c1',
      updatedAt: Date.now(),
    });

    useBrowserInspectorStore.getState().releaseTurnEngagement();

    // A panel the user opened manually must survive unrelated turns.
    expect(useBrowserInspectorStore.getState().engagedInTurn).toBe(false);
    expect(useBrowserInspectorStore.getState().isOpen).toBe(true);
    expect(useBrowserInspectorStore.getState().viewData).not.toBeNull();
  });

  it('releaseTurnEngagement fully clears state after an engaged browser turn', () => {
    useBrowserInspectorStore.getState().markTurnEngaged();
    useBrowserInspectorStore.getState().setBrowserActive(true);
    useBrowserInspectorStore.getState().openPanel();
    useBrowserInspectorStore.getState().updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/jpeg',
      refs: {},
      pageUrl: 'https://example.com',
      pageTitle: 'Example',
      viewportWidth: 1280,
      viewportHeight: 720,
      sourceChatId: 'c1',
      updatedAt: Date.now(),
    });

    useBrowserInspectorStore.getState().releaseTurnEngagement();

    const state = useBrowserInspectorStore.getState();
    expect(state.engagedInTurn).toBe(false);
    expect(state.isBrowserActive).toBe(false);
    expect(state.isOpen).toBe(false);
    expect(state.viewData).toBeNull();
    expect(state.selectedElement).toBeNull();
  });

  it('reset clears engagedInTurn', () => {
    useBrowserInspectorStore.getState().markTurnEngaged();
    useBrowserInspectorStore.getState().reset();
    expect(useBrowserInspectorStore.getState().engagedInTurn).toBe(false);
  });
});
